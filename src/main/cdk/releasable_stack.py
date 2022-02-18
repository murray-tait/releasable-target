from zipfile import ZipFile
import hashlib

from cdktf_cdktf_provider_aws.lambdafunction import (
    LambdaPermission,
    LambdaFunction,
    LambdaFunctionEnvironment,
)
from cdktf_cdktf_provider_aws.iam import (
    IamRole,
    DataAwsIamPolicyDocumentStatement,
)
from cdktf_cdktf_provider_aws.route53 import DataAwsRoute53Zone
from cdktf import (
    TerraformHclModule,
    TerraformStack,
    TerraformResourceLifecycle,
)
from cdktf_cdktf_provider_aws.cloudwatch import CloudwatchLogGroup
from cdktf_cdktf_provider_aws.sns import (
    SnsTopic,
    SnsTopicPolicy,
    SnsTopicSubscription,
    DataAwsSnsTopic,
)
from constructs import Construct

from murraytait_cdktf.shared import Shared
from murraytait_cdktf.provider_factory import ProviderFactory
from murraytait_cdktf.accounts import Accounts
from murraytait_cdktf.config import Config

from env import (
    get_environment,
    environment_certificate,
    create_backend,
    rest_api_gateway,
    attach_policy,
    create_assume_role_policy,
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

        lambda_name = "releasable"

        lambda_function = LambdaFunction(
            scope=self,
            id=f"{lambda_name}_lambda",
            function_name=lambda_name,
            runtime="provided",
            handler="bootstrap",
            timeout=30,
            role=f"arn:aws:iam::{accounts.aws_account_id}:role/{app_name}_lambda_service_role",
            s3_bucket=shared.destination_builds_bucket_name,
            s3_key=f"builds/{app_name}/refs/branch/{self.environment}/lambda.zip",
            lifecycle=TerraformResourceLifecycle(ignore_changes=["last_modified"]),
        )

        api_gateway_id = rest_api_gateway(
            self,
            "lambda",
            shared.fqdn,
            shared.web_acl_name,
            route_53_zone,
            acm_cert,
            lambda_function.invoke_arn,
        )

        create_lambda_function_support(
            self,
            app_name,
            aws_region,
            api_gateway_id,
            accounts.aws_account_id,
        )

        self.create_lambda_pipeline(
            accounts.aws_account_id,
            shared.destination_builds_bucket_name,
            shared.aws_sns_topic_env_build_notification_name,
            app_name,
            lambda_function,
            aws_region,
            ns,
            scope,
            self.environment,
        )

    def create_lambda_pipeline(
        self,
        aws_account_id,
        destination_builds_bucket_name,
        aws_sns_topic_env_build_notification_name,
        app_name,
        lambda_function,
        aws_region,
        ns,
        scope,
        environment,
    ):
        lambda_service_role_name = f"{app_name}_lambda_updater_lambda_service_role"
        assume_role_policy = create_assume_role_policy(
            self, "lambda.amazonaws.com", lambda_service_role_name
        )
        updater_lambda_name = f"{app_name}-lambda-updater"

        source_file_name = "lambda_updater.py"
        archive_file_name = "lambda_updater.zip"
        zipObj = ZipFile(scope.outdir + "/stacks/" + ns + "/" + archive_file_name, "w")
        zipObj.write(source_file_name)
        zipObj.close()

        with open(scope.outdir + "/stacks/" + ns + "/" + archive_file_name, "rb") as f:
            bytes = f.read()  # read entire file as bytes
            readable_hash = hashlib.sha256(bytes).hexdigest()

        lambda_function = LambdaFunction(
            self,
            id=f"{app_name}-lambda-updater",
            function_name=f"{app_name}-lambda-updater",
            handler="lambda_updater.updater",
            runtime="python3.7",
            role=f"arn:aws:iam::{aws_account_id}:role/{lambda_service_role_name}",
            filename=archive_file_name,
            source_code_hash=readable_hash,
            timeout=30,
            environment=LambdaFunctionEnvironment(
                variables={
                    "FUNCTION_NAMES": app_name,
                    "BRANCH_NAME": environment,
                    "APPLICATION_NAME": app_name,
                }
            ),
            lifecycle=TerraformResourceLifecycle(ignore_changes=["last_modified"]),
        )

        sns_topic = DataAwsSnsTopic(
            self,
            id="env_build_sns_topic",
            name=aws_sns_topic_env_build_notification_name,
        )

        SnsTopicSubscription(
            self,
            id="env_build_notification",
            topic_arn=sns_topic.arn,
            protocol="lambda",
            endpoint=lambda_function.arn,
        )

        lambda_service_role = IamRole(
            self,
            id=lambda_service_role_name,
            name=lambda_service_role_name,
            assume_role_policy=assume_role_policy.json,
        )

        LambdaPermission(
            self,
            id=f"{app_name}-lambda-updater_lambda_permission_api_gateway",
            statement_id=f"{app_name}-lambda-updater-api-gateway-access",
            function_name=f"{app_name}-lambda-updater",
            principal="sns.amazonaws.com",
            action="lambda:InvokeFunction",
            source_arn=sns_topic.arn,
        )

        log_write_access = DataAwsIamPolicyDocumentStatement(
            sid="logWriteAccess",
            actions=["logs:PutLogEvents", "logs:CreateLogStream"],
            resources=[
                f"arn:aws:logs:{aws_region}:{aws_account_id}:log-group:/aws/lambda/{updater_lambda_name}:*"
            ],
            effect="Allow",
        )

        lambda_update_write_access = DataAwsIamPolicyDocumentStatement(
            sid="lambdaUpdate",
            actions=["lambda:*"],
            resources=[lambda_function.arn],
            effect="Allow",
        )

        statements = [log_write_access, lambda_update_write_access]

        attach_policy(
            self, f"{app_name}_lambda_updater", lambda_service_role, statements
        )

        CloudwatchLogGroup(
            self,
            id=f"{app_name}-lambda-updater_lambda_log_group",
            name=f"/aws/lambda/{app_name}-lambda-updater",
            retention_in_days=14,
        )


def create_lambda_function_support(
    stack,
    name,
    aws_region,
    api_gateway_id,
    aws_account_id,
    extra_statements=[],
):
    lambda_service_role_name = f"{name}_lambda_service_role"
    assume_role_policy = create_assume_role_policy(
        stack, "lambda.amazonaws.com", lambda_service_role_name
    )

    lambda_service_role = IamRole(
        stack,
        id=lambda_service_role_name,
        name=lambda_service_role_name,
        assume_role_policy=assume_role_policy.json,
    )

    LambdaPermission(
        stack,
        id=f"{name}_lambda_permission_api_gateway",
        statement_id=f"{name}-api-gateway-access",
        function_name=name,
        principal="apigateway.amazonaws.com",
        action="lambda:InvokeFunction",
        source_arn=f"arn:aws:execute-api:{aws_region}:{aws_account_id}:{api_gateway_id}/*/*/*",
    )

    log_write_access = DataAwsIamPolicyDocumentStatement(
        sid="logWriteAccess",
        actions=["logs:PutLogEvents", "logs:CreateLogStream"],
        resources=[
            f"arn:aws:logs:{aws_region}:{aws_account_id}:log-group:/aws/lambda/{name}:*"
        ],
        effect="Allow",
    )

    xray_write_access = DataAwsIamPolicyDocumentStatement(
        sid="xrayWriteAccess",
        actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
        resources=["*"],
        effect="Allow",
    )

    statements = extra_statements + [
        log_write_access,
        xray_write_access,
    ]

    attach_policy(stack, f"{name}_lambda", lambda_service_role, statements)

    CloudwatchLogGroup(
        stack,
        id=f"{name}_lambda_log_group",
        name=f"/aws/lambda/{name}",
        retention_in_days=14,
    )
