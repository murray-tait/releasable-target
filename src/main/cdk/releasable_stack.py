from cdktf_cdktf_provider_aws.lambdafunction import (
    LambdaPermission,
    LambdaFunction,
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

from constructs import Construct

from murraytait_cdktf.shared import Shared
from murraytait_cdktf.provider_factory import ProviderFactory
from murraytait_cdktf.accounts import Accounts
from murraytait_cdktf.config import Config

from env import (
    get_environment,
    environment_certificate,
    create_backend,
    api_and_lambda,
    create_lambda_pipeline,
)


class ReleasableStack(TerraformStack):
    def __init__(self, scope: Construct, ns: str):

        super().__init__(scope, ns)

        environment = get_environment(scope, ns)

        config = Config(scope, ns)
        accounts = Accounts(environment, config.accounts_profile)
        shared = Shared(config, accounts, environment)
        app_name = "releasable"
        aws_region = "eu-west-1"

        create_backend(self, config, accounts, ns)

        provider_factory = ProviderFactory(
            self, config, shared.aws_role_arn, shared.aws_profile
        )
        provider_factory.build(aws_region)

        aws_global_provider = provider_factory.build(
            "us-east-1", "global_aws", "global"
        )

        route_53_zone = DataAwsRoute53Zone(
            self, id="environment", name=shared.environment_domain_name
        )

        acm_cert = environment_certificate(
            self, aws_global_provider, shared.environment_domain_name
        )

        build_artifact_key = (
            f"builds/{app_name}/refs/branch/{environment}/cloudfront.zip"
        )

        web_config = {
            "REACT_APP_API_ENDPOINT": f"https://releasable.{shared.environment_domain_name}/default",
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

        TerraformHclModule(
            self,
            id="cloudfront_pipeline",
            source="git@github.com:deathtumble/terraform_modules.git//modules/cloudfront_pipeline?ref=v0.1.42",
            variables={
                "fqdn": f"web{shared.fqdn}",
                "destination_builds_bucket_name": shared.destination_builds_bucket_name,
                "application_name": "releasable",
                "branch_name": environment,
                "artifacts_bucket_name": shared.artifacts_bucket_name,
                "build_artifact_key": build_artifact_key,
            },
        )

        lambda_name = "releasable"

        lambda_function = api_and_lambda(
            self,
            route_53_zone,
            acm_cert,
            lambda_name,
            environment,
            shared.destination_builds_bucket_name,
            shared.fqdn,
            shared.web_acl_name,
        )

        create_lambda_pipeline(
            self,
            shared.destination_builds_bucket_name,
            shared.aws_sns_topic_env_build_notification_name,
            lambda_name,
            lambda_function,
            ns,
            scope,
            environment,
        )
