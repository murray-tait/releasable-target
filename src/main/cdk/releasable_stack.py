import json
from string import Template

from cdktf_cdktf_provider_aws.eventbridge import (
    CloudwatchEventTarget,
    CloudwatchEventRule,
)
from cdktf_cdktf_provider_aws.codepipeline import (
    Codepipeline,
    CodepipelineArtifactStore,
    CodepipelineStage,
    CodepipelineStageAction,
)
from cdktf_cdktf_provider_aws.route53 import DataAwsRoute53Zone, Route53Record
from cdktf_cdktf_provider_aws.cloudfront import (
    CloudfrontDistribution,
    CloudfrontDistributionOriginS3OriginConfig,
    CloudfrontDistributionOrigin,
    CloudfrontDistributionCustomErrorResponse,
    CloudfrontOriginAccessIdentity,
    CloudfrontDistributionCustomErrorResponse,
    CloudfrontDistributionDefaultCacheBehavior,
    CloudfrontDistributionDefaultCacheBehaviorForwardedValues,
    CloudfrontDistributionDefaultCacheBehaviorForwardedValuesCookies,
    CloudfrontDistributionRestrictions,
    CloudfrontDistributionRestrictionsGeoRestriction,
    CloudfrontDistributionViewerCertificate,
)
from cdktf_cdktf_provider_aws.wafv2 import DataAwsWafv2WebAcl
from cdktf_cdktf_provider_aws.s3 import (
    S3Bucket,
    S3BucketPolicy,
    S3BucketObject,
    S3BucketPublicAccessBlock,
)
from cdktf_cdktf_provider_aws.iam import (
    DataAwsIamPolicyDocumentStatement,
    DataAwsIamPolicyDocument,
    DataAwsIamPolicyDocumentStatementPrincipals,
    IamRole,
    IamRolePolicy,
)
from cdktf import TerraformStack
from constructs import Construct

from murraytait_cdktf.shared import Shared
from murraytait_cdktf.provider_factory import ProviderFactory
from murraytait_cdktf.accounts import Accounts
from murraytait_cdktf.config import Config
from murraytait_cdktf.env import (
    get_environment,
    environment_certificate,
    create_backend,
    api_and_lambda,
    create_lambda_pipeline,
    create_assume_role_policy,
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

        build_artifact_key = f"builds/{app_name}/refs/branch/{environment}/web.zip"

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

        web_acl_name = shared.web_acl_name
        create_web_site(
            self,
            "webreleasable",
            web_config,
            f"web{shared.fqdn}",
            web_acl_name,
            route_53_zone.id,
            aws_global_provider,
            acm_cert,
        )

        artifacts_bucket_name = shared.artifacts_bucket_name
        destination_builds_bucket_name = shared.destination_builds_bucket_name
        fqdn = shared.fqdn

        self.create_cloudfront_pipeline(
            "webreleasable",
            environment,
            build_artifact_key,
            artifacts_bucket_name,
            destination_builds_bucket_name,
            f"web{shared.fqdn}",
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

    def create_cloudfront_pipeline(
        self,
        name,
        environment,
        build_artifact_key,
        artifacts_bucket_name,
        destination_builds_bucket_name,
        fqdn,
    ):

        pipeline_role_name = f"{name}-cloudfront-pipeline-CodePipeline"
        pipeline_role_name_assume_policy = create_assume_role_policy(
            self, "codepipeline.amazonaws.com", pipeline_role_name
        )

        pipeline_role = IamRole(
            self,
            id=f"{name}_pipeline_role",
            name=pipeline_role_name,
            assume_role_policy=pipeline_role_name_assume_policy.json,
        )

        pipeline = Codepipeline(
            self,
            id=f"{name}_pipeline",
            name=fqdn,
            role_arn=pipeline_role.arn,
            artifact_store=[
                CodepipelineArtifactStore(location=artifacts_bucket_name, type="S3")
            ],
            stage=[
                CodepipelineStage(
                    name="Source",
                    action=[
                        CodepipelineStageAction(
                            name="Source",
                            category="Source",
                            owner="AWS",
                            provider="S3",
                            version="1",
                            output_artifacts=[f"{name}-source_output"],
                            configuration={
                                "S3Bucket": destination_builds_bucket_name,
                                "S3ObjectKey": build_artifact_key,
                                "PollForSourceChanges": "true",
                            },
                        )
                    ],
                ),
                CodepipelineStage(
                    name="Deploy",
                    action=[
                        CodepipelineStageAction(
                            name="Deploy",
                            category="Deploy",
                            owner="AWS",
                            provider="S3",
                            version="1",
                            input_artifacts=[f"{name}-source_output"],
                            configuration={"BucketName": fqdn, "Extract": "true"},
                        )
                    ],
                ),
            ],
        )

        ###########################################################################

        cloudwatch_event_role_name = f"{fqdn}-cloudwatch"
        cloudwatch_event_assume_role_policy = create_assume_role_policy(
            self, "events.amazonaws.com", cloudwatch_event_role_name
        )

        event_role_policy_document = DataAwsIamPolicyDocument(
            self,
            id=f"{name}_event_policy_document",
            statement=[
                DataAwsIamPolicyDocumentStatement(
                    sid="xrayWriteAccess",
                    actions=["codepipeline:StartPipelineExecution"],
                    resources=[pipeline.arn],
                    effect="Allow",
                )
            ],
        )

        cloudwatch_event_role = IamRole(
            self,
            id=f"{name}_cloudwatch_role",
            name=cloudwatch_event_role_name,
            assume_role_policy=cloudwatch_event_assume_role_policy.json,
        )

        event_role_policy = IamRolePolicy(
            self,
            id=f"{name}_codewatch_role_policy",
            role=cloudwatch_event_role.id,
            policy=event_role_policy_document.json,
        )

        rule = CloudwatchEventRule(
            self,
            id=f"{name}_cloudwatch_event_rule",
            name=f"{name}_rule",
            description="Triggers CodePipeline when an a certain object is dropped in a specified S3 bucket",
            event_pattern=template(
                "events/cloudwatch_s3_write_trigger_codepipeline.json",
                {
                    "bucket_name": destination_builds_bucket_name,
                    "build_artifact_key": build_artifact_key,
                },
            ),
        )

        CloudwatchEventTarget(
            self,
            id=f"{name}_cloudwatch_event_target",
            arn=pipeline.arn,
            rule=rule.name,
            role_arn=cloudwatch_event_role.arn,
        )

        CloudwatchEventRule(
            self,
            id=f"{name}-cloud-pipeline",
            name=f"{name}-cloud-pipeline",
            description="Amazon CloudWatch Events rule to automatically start your pipeline when a change occurs in the Amazon S3 object key or S3 folder. Deleting this may prevent changes from being detected in that pipeline. Read more: http://docs.aws.amazon.com/codepipeline/latest/userguide/pipelines-about-starting.html",
            event_pattern=json.dumps(
                {
                    "source": ["aws.s3"],
                    "detail-type": ["AWS API Call via CloudTrail"],
                    "detail": {
                        "eventSource": ["s3.amazonaws.com"],
                        "eventName": [
                            "PutObject",
                            "CompleteMultipartUpload",
                            "CopyObject",
                        ],
                        "requestParameters": {
                            "bucketName": [f"{destination_builds_bucket_name}"],
                            "key": [f"{build_artifact_key}"],
                        },
                    },
                }
            ),
        )


def create_web_site(
    stack,
    name,
    web_config,
    fqdn,
    web_acl_name,
    zone_id,
    global_provider,
    acm_cert,
):
    origin_access_identity = CloudfrontOriginAccessIdentity(
        stack,
        id=f"{name}_origin_access_identity",
        comment=f"OAI For {fqdn}",
    )

    site_bucket = S3Bucket(stack, id=f"{name}_site_bucket", bucket=fqdn, acl="private")

    S3BucketPublicAccessBlock(
        stack,
        id=f"{name}_site_bucket_public_access_block",
        bucket=site_bucket.id,
        block_public_acls=True,
        block_public_policy=True,
        restrict_public_buckets=True,
        ignore_public_acls=True,
    )

    s3_object_access = DataAwsIamPolicyDocumentStatement(
        sid="s3ObjectAccess",
        actions=["s3:GetObject"],
        resources=[f"{site_bucket.arn}/*"],
        effect="Allow",
        principals=[
            DataAwsIamPolicyDocumentStatementPrincipals(
                type="AWS",
                identifiers=[origin_access_identity.iam_arn],
            )
        ],
    )

    s3_list_bucket_access = DataAwsIamPolicyDocumentStatement(
        sid="s3ListBucketAccess",
        actions=["s3:ListBucket"],
        resources=[site_bucket.arn],
        effect="Allow",
        principals=[
            DataAwsIamPolicyDocumentStatementPrincipals(
                type="AWS",
                identifiers=[origin_access_identity.iam_arn],
            )
        ],
    )

    config = json.dumps(web_config)

    S3BucketObject(
        stack,
        id=f"{name}_site_config",
        bucket=site_bucket.bucket,
        key="config.js",
        content=f"window.env = Object.assign({{}}, window.env, {config})",
    )

    policy_document = DataAwsIamPolicyDocument(
        stack,
        id=f"{name}_site_bucket_policy_document",
        statement=[s3_object_access, s3_list_bucket_access],
    )

    S3BucketPolicy(
        stack,
        id=f"{name}_site_bucket_policy",
        bucket=site_bucket.id,
        policy=policy_document.json,
    )

    waf_acl = DataAwsWafv2WebAcl(
        stack,
        id=f"{name}_web_wafv2_acl",
        name=web_acl_name,
        scope="CLOUDFRONT",
        provider=global_provider,
    )

    cloud_front_dist = CloudfrontDistribution(
        stack,
        id=f"{name}_cloudfront_dist",
        enabled=True,
        is_ipv6_enabled=True,
        comment=f"Cloudfront distribution for {fqdn}",
        default_root_object="index.html",
        price_class="PriceClass_100",
        web_acl_id=waf_acl.arn,
        origin=[
            CloudfrontDistributionOrigin(
                domain_name=site_bucket.bucket_regional_domain_name,
                origin_id=f"{site_bucket.id}-origin",
                s3_origin_config=CloudfrontDistributionOriginS3OriginConfig(
                    origin_access_identity=origin_access_identity.cloudfront_access_identity_path
                ),
            )
        ],
        custom_error_response=[
            CloudfrontDistributionCustomErrorResponse(
                error_caching_min_ttl=300,
                error_code=404,
                response_code=200,
                response_page_path="/index.html",
            )
        ],
        aliases=[fqdn],
        default_cache_behavior=CloudfrontDistributionDefaultCacheBehavior(
            min_ttl=0,
            default_ttl=0,
            max_ttl=0,
            target_origin_id=f"{site_bucket.id}-origin",
            viewer_protocol_policy="redirect-to-https",
            allowed_methods=["GET", "HEAD"],
            cached_methods=["GET", "HEAD"],
            forwarded_values=CloudfrontDistributionDefaultCacheBehaviorForwardedValues(
                query_string=False,
                cookies=CloudfrontDistributionDefaultCacheBehaviorForwardedValuesCookies(
                    forward="none",
                ),
            ),
        ),
        restrictions=CloudfrontDistributionRestrictions(
            geo_restriction=CloudfrontDistributionRestrictionsGeoRestriction(
                restriction_type="whitelist",
                locations=["GB", "IE"],
            )
        ),
        viewer_certificate=CloudfrontDistributionViewerCertificate(
            acm_certificate_arn=acm_cert.arn,
            ssl_support_method="sni-only",
            minimum_protocol_version="TLSv1.2_2018",
        ),
    )

    Route53Record(
        stack,
        id=f"{name}_site_route_53_record",
        zone_id=zone_id,
        name=fqdn,
        type="CNAME",
        ttl=300,
        records=[cloud_front_dist.domain_name],
    )


def template(template_file_name, dict):
    with open(template_file_name, "r") as file:
        policy = Template(file.read()).substitute(dict)
    return policy
