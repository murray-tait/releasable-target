from constructs import Construct
from cdktf import TerraformHclModule
from cdktf_cdktf_provider_archive import ArchiveProvider
from cdktf_cdktf_provider_aws import AwsProvider, AwsProviderAssumeRole

from base_stack import BaseStack


class CommonStack(BaseStack):

    def __init__(self, app: Construct, ns: str):
        super().__init__(app, ns)

        self.common = TerraformHclModule(
            self,
            id="common",
            source="../../terraform/modules/common/",
            variables={
                "application_name": self.app_name,
                "project_name": "experiment",
                "domain": self.tldn,
                "aws_account_id": self.aws_account_id,
                "dns_account_id": self.dns_account_id,
                "build_account_id": self.build_account_id,
                "build_account_name": self.build_account_name,
                "terraform_state_account_name": self.terraform_state_account_name,
                "terraform_state_account_id": self.terraform_state_account_id})

        self.fqdn = self.common.get_string("fqdn")
        self.aws_region = self.common.get_string("aws_region")
        self.destination_builds_bucket_name = self.common.get_string(
            "destination_builds_bucket_name")
        self.fqdn_no_app = self.common.get_string("fqdn_no_app")
        self.aws_role_arn = self.common.get_string("aws_role_arn")
        self.aws_profile = self.common.get_string("aws_profile")
        self.web_acl_name = self.common.get_string("web_acl_name")
        self.aws_global_provider = self.create_providers()

    def create_providers(self):
        profile = None
        assume_role = None
        if self.use_role_arn:
            assume_role = AwsProviderAssumeRole(
                self, role_arn=self.aws_role_arn)
        else:
            profile = self.aws_profile

        AwsProvider(
            self, id="aws", region="eu-west-1", profile=profile, assume_role=assume_role)

        aws_global_provider = AwsProvider(
            self, id="global_aws", region="us-east-1", profile=profile, assume_role=assume_role, alias="global"
        )

        ArchiveProvider(self, "archive")

        return aws_global_provider

    def _get_fqdn(self):
        if self.environment == "prod":
            fqdn_list = [self.app_name] + self.tldn.split(".")
        else:
            fqdn_list = [self.app_name] + \
                [self.environment] + self.tldn.split(".")
        return ".".join(fqdn_list)
