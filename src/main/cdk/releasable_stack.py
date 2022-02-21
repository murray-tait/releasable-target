import json

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
)
from cdktf import TerraformHclModule, TerraformStack
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

        web_acl_name = shared.web_acl_name
        self.create_web_site(
            "webreleasable",
            web_config,
            f"web{shared.fqdn}",
            web_acl_name,
            route_53_zone.id,
            aws_global_provider,
            acm_cert,
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

    def create_web_site(
        self,
        name,
        web_config,
        fqdn,
        web_acl_name,
        zone_id,
        global_provider,
        acm_cert,
    ):
        origin_access_identity = CloudfrontOriginAccessIdentity(
            self,
            id=f"{name}_origin_access_identity",
            comment=f"OAI For {fqdn}",
        )

        site_bucket = S3Bucket(
            self, id=f"{name}_site_bucket", bucket=fqdn, acl="private"
        )

        S3BucketPublicAccessBlock(
            self,
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
            self,
            id=f"{name}_site_config",
            bucket=site_bucket.bucket,
            key="config.js",
            content=f"window.env = Object.assign({{}}, window.env, {config})",
        )

        policy_document = DataAwsIamPolicyDocument(
            self,
            id=f"{name}_site_bucket_policy_document",
            statement=[s3_object_access, s3_list_bucket_access],
        )

        S3BucketPolicy(
            self,
            id=f"{name}_site_bucket_policy",
            bucket=site_bucket.id,
            policy=policy_document.json,
        )

        waf_acl = DataAwsWafv2WebAcl(
            self,
            id=f"{name}_web_wafv2_acl",
            name=web_acl_name,
            scope="CLOUDFRONT",
            provider=global_provider,
        )

        cloud_front_dist = CloudfrontDistribution(
            self,
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
            self,
            id=f"{name}_site_route_53_record",
            zone_id=zone_id,
            name=fqdn,
            type="CNAME",
            ttl=300,
            records=[cloud_front_dist.domain_name],
        )
