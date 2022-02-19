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
from cdktf_cdktf_provider_aws.cloudwatch import CloudwatchLogGroup
from cdktf_cdktf_provider_aws.acm import DataAwsAcmCertificate
from constructs import Construct
from cdktf import S3Backend
from cdktf_cdktf_provider_aws.wafregional import DataAwsWafregionalWebAcl
from cdktf_cdktf_provider_aws.route53 import Route53Record, Route53RecordAlias
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

    return api_gateway.id


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
    )

    IamRolePolicyAttachment(
        stack,
        id=f"{name}_role_policy_attachment",
        role=lambda_service_role.name,
        policy_arn=lambda_log_access.arn,
    )
