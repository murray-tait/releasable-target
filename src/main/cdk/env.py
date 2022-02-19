#!/usr/bin/env python
import os
import json
from json import JSONEncoder
from zipfile import ZipFile
import hashlib
from base64 import b64encode

from cdktf import TerraformResourceLifecycle
from cdktf_cdktf_provider_aws.wafregional import (
    WafregionalWebAclAssociation,
)
from cdktf_cdktf_provider_aws.iam import (
    IamRole,
    DataAwsIamPolicyDocumentStatement,
)
from cdktf_cdktf_provider_aws.cloudwatch import CloudwatchLogGroup
from cdktf_cdktf_provider_aws.acm import DataAwsAcmCertificate
from constructs import Construct
from cdktf import S3Backend
from cdktf_cdktf_provider_aws.wafregional import DataAwsWafregionalWebAcl
from cdktf_cdktf_provider_aws.route53 import Route53Record, Route53RecordAlias
from cdktf_cdktf_provider_aws.lambdafunction import (
    LambdaPermission,
    LambdaFunction,
    LambdaFunctionEnvironment,
)
from cdktf_cdktf_provider_aws.apigateway import (
    ApiGatewayRestApi,
    ApiGatewayRestApiEndpointConfiguration,
    ApiGatewayDeployment,
    ApiGatewayRestApiPolicy,
    ApiGatewayStage,
    ApiGatewayStageAccessLogSettings,
    ApiGatewayBasePathMapping,
    ApiGatewayMethod,
    ApiGatewayMethodSettings,
    ApiGatewayMethodSettingsSettings,
    ApiGatewayResource,
    ApiGatewayIntegration,
    ApiGatewayDomainName,
)
from cdktf_cdktf_provider_aws.s3 import DataAwsS3Bucket
from cdktf_cdktf_provider_aws.sns import (
    SnsTopicSubscription,
    DataAwsSnsTopic,
)
from cdktf_cdktf_provider_aws.iam import (
    IamRolePolicyAttachment,
    IamPolicy,
    DataAwsIamPolicyDocumentStatement,
    DataAwsIamPolicyDocument,
    DataAwsIamPolicyDocumentStatementPrincipals,
)


def get_environment(scope: Construct, ns: str):
    environment = None
    with open(
        scope.outdir + "/stacks/" + ns + "/.terraform/environment", "r"
    ) as reader:
        environment = reader.read().split()[0]
    return environment


def environment_certificate(scope, provider, environment_domain_name):
    acm_cert = DataAwsAcmCertificate(
        scope,
        id="main_cert",
        domain=f"*.{environment_domain_name}",
        types=["AMAZON_ISSUED"],
        statuses=["ISSUED"],
        provider=provider,
        most_recent=True,
    )

    return acm_cert


def file(file_name: str) -> str:
    package_directory = os.path.dirname(os.path.abspath(__file__))
    full_file_name = os.path.join(package_directory, file_name)
    f = open(full_file_name, "r")
    return f.read()


def create_backend(stack, config, accounts, ns):
    bucket = config.tldn + "." + accounts.terraform_state_account_name + ".terraform"
    dynamo_table = (
        config.tldn + "." + accounts.terraform_state_account_name + ".terraform.lock"
    )

    backend_args = {
        "region": "eu-west-1",
        "key": ns + "/terraform.tfstate",
        "bucket": bucket,
        "dynamodb_table": dynamo_table,
        "acl": "bucket-owner-full-control",
    }

    if config.use_role_arn:
        backend_args["role_arn"] = (
            "arn:aws:iam::"
            + accounts.terraform_state_account_id
            + ":role/TerraformStateAccess"
        )
    else:
        backend_args["profile"] = (
            accounts.terraform_state_account_id + "_TerraformStateAccess"
        )

    S3Backend(stack, **backend_args)


def create_lambda_pipeline(
    stack,
    destination_builds_bucket_name,
    aws_sns_topic_env_build_notification_name,
    app_name,
    lambda_function,
    ns,
    scope,
    environment,
):
    destination_builds_bucket = DataAwsS3Bucket(
        stack, id="destination_builds_bucket", bucket=destination_builds_bucket_name
    )

    s3_object_read_access = DataAwsIamPolicyDocumentStatement(
        sid="s3ObjectRead",
        actions=["s3:GetObject"],
        resources=[f"{destination_builds_bucket.arn}/*"],
        effect="Allow",
    )

    s3_bucket_read_access = DataAwsIamPolicyDocumentStatement(
        sid="s3BucketRead",
        actions=["s3:ListBucket"],
        resources=[destination_builds_bucket.arn],
        effect="Allow",
    )

    lambda_update_write_access = DataAwsIamPolicyDocumentStatement(
        sid="lambdaUpdate",
        actions=["lambda:UpdateFunctionCode"],
        resources=[lambda_function.arn],
        effect="Allow",
    )

    extra_statements = [
        s3_object_read_access,
        s3_bucket_read_access,
        lambda_update_write_access,
    ]

    source_file_name = "lambda_updater.py"
    archive_file_name = "lambda_updater.zip"
    readable_hash = prepare_zip(ns, scope, source_file_name, archive_file_name)

    sns_topic = DataAwsSnsTopic(
        stack,
        id="env_build_sns_topic",
        name=aws_sns_topic_env_build_notification_name,
    )

    lambda_name = f"{app_name}_lambda_updater"
    principal = "sns.amazonaws.com"
    source_arn = sns_topic.arn
    lambda_service_role_name = f"{lambda_name}_lambda_service_role"
    service = "lambda.amazonaws.com"
    lambda_service_role = create_role_with_service_assumption(
        stack, lambda_service_role_name, service
    )

    updater_lambda_function = LambdaFunction(
        stack,
        id=lambda_name,
        function_name=lambda_name,
        handler="lambda_updater.updater",
        runtime="python3.7",
        role=lambda_service_role.arn,
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

    SnsTopicSubscription(
        stack,
        id="env_build_notification",
        topic_arn=sns_topic.arn,
        protocol="lambda",
        endpoint=updater_lambda_function.arn,
    )

    create_inner_lambda_support(
        stack, extra_statements, lambda_name, principal, source_arn, lambda_service_role
    )


def api_and_lambda(
    stack,
    route_53_zone,
    acm_cert,
    lambda_name,
    environment,
    destination_builds_bucket_name,
    fqdn,
    web_acl_name,
):
    lambda_service_role = create_role_with_service_assumption(
        stack, f"{lambda_name}_lambda_service_role", "lambda.amazonaws.com"
    )

    lambda_function = LambdaFunction(
        scope=stack,
        id=f"{lambda_name}_lambda",
        function_name=lambda_name,
        runtime="provided",
        handler="bootstrap",
        timeout=30,
        role=lambda_service_role.arn,
        s3_bucket=destination_builds_bucket_name,
        s3_key=f"builds/{lambda_name}/refs/branch/{environment}/lambda.zip",
        lifecycle=TerraformResourceLifecycle(ignore_changes=["last_modified"]),
    )

    execution_arn = rest_api_gateway(
        stack,
        "lambda",
        fqdn,
        web_acl_name,
        route_53_zone,
        acm_cert,
        lambda_function.invoke_arn,
    )

    xray_write_access = DataAwsIamPolicyDocumentStatement(
        sid="xrayWriteAccess",
        actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
        resources=["*"],
        effect="Allow",
    )

    extra_statements = [xray_write_access]

    create_inner_lambda_support(
        stack,
        extra_statements,
        lambda_name,
        "apigateway.amazonaws.com",
        execution_arn,
        lambda_service_role,
    )
    return lambda_function


def rest_api_gateway(
    stack, id, fqdn, web_acl_name, route_53_zone, acm_cert, invoke_arn
):
    encoder = JSONEncoder()

    def encode(o):
        return encoder.encode(o.to_terraform())

    aws_wafregional_web_acl = DataAwsWafregionalWebAcl(
        stack, id="main", name=web_acl_name
    )

    api_gateway = ApiGatewayRestApi(
        stack,
        id=f"{id}_api",
        name=fqdn,
        description=f"API Gateway for {fqdn}",
        endpoint_configuration=ApiGatewayRestApiEndpointConfiguration(
            types=["REGIONAL"]
        ),
    )

    proxy_resource = ApiGatewayResource(
        stack,
        id=f"{id}_api_proxy_resource",
        rest_api_id=api_gateway.id,
        parent_id=api_gateway.root_resource_id,
        path_part="{proxy+}",
    )

    proxy_method = ApiGatewayMethod(
        stack,
        id=f"{id}_api_proxy_method",
        rest_api_id=api_gateway.id,
        resource_id=proxy_resource.id,
        http_method="ANY",
        authorization="NONE",
        api_key_required=False,
    )

    proxy_integration = ApiGatewayIntegration(
        stack,
        id=f"{id}_api_proxy_intergration",
        rest_api_id=api_gateway.id,
        resource_id=proxy_resource.id,
        http_method="ANY",
        integration_http_method="POST",
        content_handling="CONVERT_TO_TEXT",
        type="AWS_PROXY",
        uri=invoke_arn,
    )

    deployment = ApiGatewayDeployment(
        stack,
        id=f"{id}_api_deployment",
        rest_api_id=api_gateway.id,
        triggers={
            "resource": encode(proxy_resource),
            "method": encode(proxy_method),
            "integration": encode(proxy_integration),
        },
        lifecycle=TerraformResourceLifecycle(create_before_destroy=True),
    )

    log_group = CloudwatchLogGroup(
        stack,
        id=f"{id}_api_gateway_log_group",
        name=f"API-Gateway-Execution-Logs_{api_gateway.id}/default",
        retention_in_days=7,
    )

    stage = ApiGatewayStage(
        stack,
        id=f"{id}_api_gateway_stage",
        stage_name="default",
        rest_api_id=api_gateway.id,
        deployment_id=deployment.id,
        cache_cluster_enabled=False,
        cache_cluster_size="0.5",
        access_log_settings=ApiGatewayStageAccessLogSettings(
            destination_arn=log_group.arn,
            format='$context.identity.sourceIp $context.identity.caller $context.identity.user [$context.requestTime] "$context.httpMethod $context.resourcePath $context.protocol" $context.status $context.responseLength $context.requestId',
        ),
        tags={},
        xray_tracing_enabled=False,
    )

    WafregionalWebAclAssociation(
        stack,
        id=f"{id}_api_gateway_stage_waf_association",
        resource_arn=stage.arn,
        web_acl_id=aws_wafregional_web_acl.id,
    )

    domain_name = ApiGatewayDomainName(
        stack,
        id=f"{id}_permission_api_gateway_domain_name",
        certificate_arn=acm_cert.arn,
        domain_name=fqdn,
        security_policy="TLS_1_2",
    )

    ApiGatewayBasePathMapping(
        stack,
        id=f"{id}_permission_api_gateway_base_path_mapping",
        api_id=api_gateway.id,
        stage_name=stage.stage_name,
        domain_name=domain_name.domain_name,
    )

    Route53Record(
        stack,
        id=f"{id}_api_gateway_route53_record",
        name=fqdn,
        type="A",
        zone_id=route_53_zone.id,
        alias=[
            Route53RecordAlias(
                evaluate_target_health=True,
                name=domain_name.cloudfront_domain_name,
                zone_id=domain_name.cloudfront_zone_id,
            )
        ],
    )

    ApiGatewayMethodSettings(
        stack,
        id=f"{id}_api_gateway_method_settings",
        rest_api_id=api_gateway.id,
        stage_name=stage.stage_name,
        method_path="*/*",
        settings=ApiGatewayMethodSettingsSettings(
            metrics_enabled=True, logging_level="INFO"
        ),
    )

    ApiGatewayRestApiPolicy(
        stack,
        id=f"{id}_api_gateway_api_policy",
        rest_api_id=api_gateway.id,
        policy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "execute-api:Invoke",
                        "Resource": f"{api_gateway.execution_arn}/*",
                    }
                ],
            }
        ),
    )

    return f"{api_gateway.execution_arn}/*/*/*"


def create_role_with_service_assumption(stack, lambda_service_role_name, service):
    assume_role_policy = create_assume_role_policy(
        stack, service, lambda_service_role_name
    )

    lambda_service_role = IamRole(
        stack,
        id=lambda_service_role_name,
        name=lambda_service_role_name,
        assume_role_policy=assume_role_policy.json,
    )

    return lambda_service_role


def create_assume_role_policy(stack, service_id, lambda_service_role_name):
    assume_role_policy = DataAwsIamPolicyDocument(
        stack,
        id=f"{lambda_service_role_name}_assume_role_policy",
        statement=[
            DataAwsIamPolicyDocumentStatement(
                actions=["sts:AssumeRole"],
                effect="Allow",
                principals=[
                    DataAwsIamPolicyDocumentStatementPrincipals(
                        identifiers=[service_id], type="Service"
                    )
                ],
            )
        ],
    )

    return assume_role_policy


def create_inner_lambda_support(
    stack, extra_statements, lambda_name, principal, source_arn, lambda_service_role
):
    LambdaPermission(
        stack,
        id=f"{lambda_name}_lambda_permission",
        statement_id=f"{lambda_name}",
        function_name=lambda_name,
        principal=principal,
        action="lambda:InvokeFunction",
        source_arn=source_arn,
    )

    log_group = CloudwatchLogGroup(
        stack,
        id=f"{lambda_name}_lambda_log_group",
        name=f"/aws/lambda/{lambda_name}",
        retention_in_days=14,
    )

    log_write_access = DataAwsIamPolicyDocumentStatement(
        sid="logWriteAccess",
        actions=["logs:PutLogEvents", "logs:CreateLogStream"],
        resources=[f"{log_group.arn}:*"],
        effect="Allow",
    )

    statements = extra_statements + [log_write_access]

    attach_policy(stack, lambda_name, lambda_service_role, statements)


def attach_policy(stack, name, lambda_service_role, statements):
    policy_document = DataAwsIamPolicyDocument(
        stack,
        id=f"{name}_policy_document",
        statement=statements,
    )

    lambda_log_access = IamPolicy(
        stack,
        id=f"{name}_policy",
        name=f"{name}_policy",
        policy=policy_document.json,
        tags={},
    )

    IamRolePolicyAttachment(
        stack,
        id=f"{name}_role_policy_attachment",
        role=lambda_service_role.name,
        policy_arn=lambda_log_access.arn,
    )


def prepare_zip(ns, scope, source_file_name, archive_file_name):
    zipObj = ZipFile(scope.outdir + "/stacks/" + ns + "/" + archive_file_name, "w")
    zipObj.write(source_file_name)
    zipObj.close()

    with open(scope.outdir + "/stacks/" + ns + "/" + archive_file_name, "rb") as f:
        bytes = f.read()
        sha = hashlib.sha256(bytes)
        digest = sha.digest()
        hash = b64encode(digest).decode()
    return hash
