from constructs import Construct
from cdktf import App, TerraformHclModule

from base_stack import BaseStack


class CommonStack(BaseStack):

    def __init__(self, scope: Construct, ns: str):
        super().__init__(scope, ns)

        self.common = TerraformHclModule(
            self,
            id="common",
            source="../../../../terraform/modules/common/",
            variables={
                "application_name": "build",
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
