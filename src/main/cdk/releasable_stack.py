import json
from json import JSONEncoder
from hashlib import sha1
from sre_constants import SRE_FLAG_MULTILINE

from cdktf_cdktf_provider_aws.lambdafunction import LambdaPermission
from cdktf_cdktf_provider_aws.secretsmanager import DataAwsSecretsmanagerSecretVersion
from cdktf_cdktf_provider_aws.lambdafunction import LambdaFunction
from cdktf_cdktf_provider_aws.iam import IamRole, IamRolePolicyAttachment, IamPolicy
from cdktf_cdktf_provider_aws.route53 import DataAwsRoute53Zone, Route53Record
from cdktf_cdktf_provider_aws.wafregional import (
    DataAwsWafregionalWebAcl,
    WafregionalWebAclAssociation,
)
from cdktf import TerraformHclModule, TerraformLocal, TerraformStack
from cdktf_cdktf_provider_aws.cloudwatch import CloudwatchLogGroup
from cdktf_cdktf_provider_aws.apigateway import (
    ApiGatewayRestApi,
    ApiGatewayRestApiEndpointConfiguration,
    ApiGatewayDeployment,
    ApiGatewayRestApiPolicy,
    ApiGatewayStage,
    ApiGatewayBasePathMapping,
    ApiGatewayMethod,
    ApiGatewayMethodSettings,
    ApiGatewayResource,
    ApiGatewayIntegration,
    ApiGatewayDomainName,
)
from constructs import Construct

from murraytait_cdktf.shared import Shared
from murraytait_cdktf.provider_factory import ProviderFactory
from murraytait_cdktf.accounts import Accounts
from murraytait_cdktf.config import Config

from env import get_environment, file, environment_certificate, create_backend


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

        aws_wafregional_web_acl_main = DataAwsWafregionalWebAcl(
            self, id="main", name=shared.web_acl_name
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

        lambda_function = LambdaFunction(
            scope=self,
            id="lambda",
            function_name=app_name,
            runtime="provided",
            handler="bootstrap",
            timeout=30,
            role=lambda_service_role.arn,
            s3_bucket=shared.destination_builds_bucket_name,
            s3_key=f"builds/{app_name}/refs/branch/{self.environment}/lambda.zip",
        )

        TerraformHclModule(
            self,
            id="lambda_pipeline",
            source="git@github.com:deathtumble/terraform_modules.git//modules/lambda_pipeline?ref=v0.4.2",
            # source="../../../../terraform/modules/lambda_pipeline",
            variables={
                "application_name": app_name,
                "destination_builds_bucket_name": shared.destination_builds_bucket_name,
                "function_names": [lambda_function.function_name],
                "function_arns": [lambda_function.arn],
                "aws_sns_topic_env_build_notification_name": shared.aws_sns_topic_env_build_notification_name,
                "aws_account_id": accounts.aws_account_id,
            },
        )

        acm_cert = environment_certificate(
            self, self.aws_global_provider, shared.environment_domain_name
        )

        api_gateway_module = TerraformHclModule(
            self,
            id="api_gateway",
            source="git@github.com:deathtumble/terraform_modules.git//modules/api_gateway?ref=v0.4.2",
            # source="../../../../terraform/modules/api_gateway",
            variables={
                "aws_region": aws_region,
                "fqdn": shared.fqdn,
                "zone_id": route_53_zone.id,
                "web_acl_id": aws_wafregional_web_acl_main.id,
                "certificate_arn": acm_cert.arn,
                "lambda_invoke_arn": lambda_function.invoke_arn,
            },
        )

        terraform_build_artifact_key = (
            f"builds/{app_name}/refs/branch/{self.environment}/terraform.zip"
        )
        TerraformLocal(
            self, "terraform_build_artifact_key", terraform_build_artifact_key
        )
        build_artifact_key = (
            f"builds/{app_name}/refs/branch/{self.environment}/cloudfront.zip"
        )
        TerraformLocal(self, "build_artifact_key", build_artifact_key)

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
        TerraformLocal(self, "web_config", web_config)

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

        DataAwsSecretsmanagerSecretVersion(
            self, id="repo_token", secret_id="repo_token"
        )

        api_gateway_id = api_gateway_module.get_string("api_id")

        LambdaPermission(
            self,
            id="lambda_permission_api_gateway",
            statement_id="releasable-api-gateway-access",
            function_name="releasable",
            principal="apigateway.amazonaws.com",
            action="lambda:InvokeFunction",
            source_arn=f"arn:aws:execute-api:eu-west-1:481652375433:{api_gateway_id}/*/*/*",
        )

        lambda_log_access = IamPolicy(
            self,
            id="lambda_log_access_policy",
            name="releasable-lambda-CloudWatchWriteAccess",
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Action": ["logs:PutLogEvents", "logs:CreateLogStream"],
                            "Resource": f"arn:aws:logs:{aws_region}:{accounts.aws_account_id}:log-group:/aws/lambda/{app_name}:*",
                            "Effect": "Allow",
                        },
                        {
                            "Action": [
                                "xray:PutTraceSegments",
                                "xray:PutTelemetryRecords",
                            ],
                            "Resource": "*",
                            "Effect": "Allow",
                        },
                    ],
                }
            ),
        )

        IamRolePolicyAttachment(
            self,
            id="lambda_log_access_role_policy_attachement",
            role=lambda_service_role.name,
            policy_arn=lambda_log_access.arn,
        )

        CloudwatchLogGroup(
            self,
            id="lambda_log_group",
            name=f"/aws/lambda/{lambda_function.function_name}",
            retention_in_days=14,
        )

        api_gateway = ApiGatewayRestApi(
            self,
            id="lambda_api",
            description=f"API Gateway for ${config.tldn}",
            endpoint_configuration=ApiGatewayRestApiEndpointConfiguration(
                types=["Regional"]
            ),
        )
        
        aws_api_gateway_resource=ApiGatewayResource(
            self,
            id="lambda_api_proxy_resource",
            rest_api_id=api_gateway.id,
            parent_id=api_gateway.root_resource_id,
            path_part="{proxy+}"
        )
        
        
        aws_api_gateway_method=ApiGatewayMethod(
            self,
            id="lambda_api_proxy_method",
            rest_api_id=api_gateway.id,
            resource_id=aws_api_gateway_resource.id,
            http_method="ANY",
            authorization="NONE",
            api_key_required=False
        )
        
        aws_api_gateway_integration=ApiGatewayIntegration(
            self,
            id="lambda_api_proxy_intergration",
            rest_api_id=api_gateway.id,
            resource_id=aws_api_gateway_resource.id,
            http_method="ANY",
            integration_http_method="POST",
            content_handling="CONVERT_TO_TEXT",
            type="AWS_PROXY",
            uri=lambda_function.lambda_invoke_arn
        )
        
        ApiGatewayDeployment(
            self,
            id="lambda_api_deployment",
            rest_api_id=api_gateway.id,
            triggers={
                "redeployment": sha1(JSONEncoder.encode([
                    aws_api_gateway_resource.proxy,
                    aws_api_gateway_method.proxy,
                    aws_api_gateway_integration.proxy
                ]))                
            }            
        )
