import json

from cdktf_cdktf_provider_aws.lambdafunction import LambdaPermission, LambdaFunction
from cdktf_cdktf_provider_aws.iam import (
    IamRole,
    IamRolePolicyAttachment,
    IamPolicy,
    DataAwsIamPolicyDocumentStatement,
    DataAwsIamPolicyDocument,
)
from cdktf_cdktf_provider_aws.route53 import DataAwsRoute53Zone
from cdktf import (
    TerraformHclModule,
    TerraformStack,
    TerraformResourceLifecycle,
)
from cdktf_cdktf_provider_aws.cloudwatch import CloudwatchLogGroup
from constructs import Construct

from murraytait_cdktf.shared import Shared
from murraytait_cdktf.provider_factory import ProviderFactory
from murraytait_cdktf.accounts import Accounts
from murraytait_cdktf.config import Config

from env import (
    get_environment,
    file,
    environment_certificate,
    create_backend,
    rest_api_gateway,
)


class ReleasableStack(TerraformStack):
    def __init__(self, scope: Construct, ns: str):

        super().__init__(scope, ns)
        self._ns = ns
        self.environment = get_environment(scope, ns)

        config = Config(scope, ns)
        accounts = Accounts(self.environment, config.accounts_profile)
        shared = Shared(config, accounts, self.environment)
        app_name = "releasable"
        aws_region = "eu-west-1"

        create_backend(self, config, accounts, ns)

        provider_factory = ProviderFactory(
            self, config, shared.aws_role_arn, shared.aws_profile
        )
        provider_factory.build(aws_region)

        self.aws_global_provider = provider_factory.build(
            "us-east-1", "global_aws", "global"
        )

        route_53_zone = DataAwsRoute53Zone(
            self, id="environment", name=shared.environment_domain_name
        )

        lambda_service_role = IamRole(
            self,
            id="lambda_service_role",
            name=f"{app_name}-lambda-executeRole",
            assume_role_policy=file("policies/lambda_service_role.json"),
        )

        acm_cert = environment_certificate(
            self, self.aws_global_provider, shared.environment_domain_name
        )

        build_artifact_key = (
            f"builds/{app_name}/refs/branch/{self.environment}/cloudfront.zip"
        )

        TerraformHclModule(
            self,
            id="cloudfront_pipeline",
            source="git@github.com:deathtumble/terraform_modules.git//modules/cloudfront_pipeline?ref=v0.1.42",
            variables={
                "fqdn": f"web{shared.fqdn}",
                "destination_builds_bucket_name": shared.destination_builds_bucket_name,
                "application_name": "releasable",
                "branch_name": self.environment,
                "artifacts_bucket_name": shared.artifacts_bucket_name,
                "build_artifact_key": build_artifact_key,
            },
        )

        web_config = {
            "REACT_APP_API_ENDPOINT": f"https://releasable.{shared.environment_domain_name}/query",
            "REACT_APP_PRIMARY_SLDN": shared.environment_domain_name,
            "REACT_APP_API_SLDN": shared.environment_domain_name,
            "REACT_APP_SSO_COOKIE_SLDN": shared.environment_domain_name,
            "REACT_APP_AWS_COGNITO_REGION": aws_region,
            "REACT_APP_AWS_COGNITO_IDENTITY_POOL_REGION": aws_region,
            "REACT_APP_AWS_COGNITO_AUTH_FLOW_TYPE": "USER_SRP_AUTH",
            "REACT_APP_AWS_COGNITO_COOKIE_EXPIRY_MINS": 55,
            "REACT_APP_AWS_COGNITO_COOKIE_SECURE": True,
        }

        TerraformHclModule(
            self,
            id="web",
            source="git@github.com:deathtumble/terraform_modules.git//modules/web?ref=v0.4.1",
            variables={
                "aws_profile": shared.aws_profile,
                "fqdn": f"web{shared.fqdn}",
                "fqdn_no_app": shared.environment_domain_name,
                "web_acl_name": shared.web_acl_name,
                "application_name": "releasable",
                "environment_config": web_config,
            },
        )

        api_gateway_id = rest_api_gateway(
            self,
            "lambda",
            shared.fqdn,
            shared.web_acl_name,
            route_53_zone,
            acm_cert,
            aws_region,
            accounts.aws_account_id,
            app_name,
        )

        create_lambda_function(
            self,
            app_name,
            aws_region,
            lambda_service_role,
            api_gateway_id,
            accounts.aws_account_id,
            shared.destination_builds_bucket_name,
            self.environment,
            shared.aws_sns_topic_env_build_notification_name,
        )


def create_lambda_function(
    stack,
    name,
    aws_region,
    lambda_service_role,
    api_gateway_id,
    aws_account_id,
    destination_builds_bucket_name,
    environment,
    aws_sns_topic_env_build_notification_name,
    extra_statement=[],
):
    lambda_function = LambdaFunction(
        scope=stack,
        id="lambda",
        function_name=name,
        runtime="provided",
        handler="bootstrap",
        timeout=30,
        role=lambda_service_role.arn,
        s3_bucket=destination_builds_bucket_name,
        s3_key=f"builds/{name}/refs/branch/{environment}/lambda.zip",
        lifecycle=TerraformResourceLifecycle(ignore_changes=["last_modified"]),
    )

    TerraformHclModule(
        stack,
        id="lambda_pipeline",
        source="git@github.com:deathtumble/terraform_modules.git//modules/lambda_pipeline?ref=v0.4.2",
        # source="../../../../terraform/modules/lambda_pipeline",
        variables={
            "application_name": name,
            "destination_builds_bucket_name": destination_builds_bucket_name,
            "function_names": [lambda_function.function_name],
            "function_arns": [lambda_function.arn],
            "aws_sns_topic_env_build_notification_name": aws_sns_topic_env_build_notification_name,
            "aws_account_id": aws_account_id,
        },
    )
    LambdaPermission(
        stack,
        id="lambda_permission_api_gateway",
        statement_id="releasable-api-gateway-access",
        function_name=name,
        principal="apigateway.amazonaws.com",
        action="lambda:InvokeFunction",
        source_arn=f"arn:aws:execute-api:{aws_region}:{aws_account_id}:{api_gateway_id}/*/*/*",
    )

    policy_document = DataAwsIamPolicyDocument(
        stack,
        id="lambda_log_access_policy_document",
        statement=extra_statement
        + [
            DataAwsIamPolicyDocumentStatement(
                actions=["logs:PutLogEvents", "logs:CreateLogStream"],
                resources=[
                    f"arn:aws:logs:{aws_region}:{aws_account_id}:log-group:/aws/lambda/{name}:*"
                ],
                effect="Allow",
            ),
            DataAwsIamPolicyDocumentStatement(
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
                effect="Allow",
            ),
        ],
    )

    lambda_log_access = IamPolicy(
        stack,
        id="lambda_log_access_policy",
        name="releasable-lambda-CloudWatchWriteAccess",
        policy=policy_document.json,
    )

    IamRolePolicyAttachment(
        stack,
        id="lambda_log_access_role_policy_attachement",
        role=lambda_service_role.name,
        policy_arn=lambda_log_access.arn,
    )

    CloudwatchLogGroup(
        stack,
        id="lambda_log_group",
        name=f"/aws/lambda/{name}",
        retention_in_days=14,
    )
