from constructs import Construct
from cdktf import TerraformHclModule
from cdktf_cdktf_provider_archive import ArchiveProvider
from cdktf_cdktf_provider_aws import AwsProvider, AwsProviderAssumeRole

from config import Config
from accounts import Accounts


class Shared():

    def __init__(self, config: Config, accounts: Accounts, environment):

        fqdn_as_list = self.get_fqdn_as_list(config, environment)

        self.fqdn = ".".join(fqdn_as_list)
        self.fqdn_reverse = ".".join(reverse(fqdn_as_list))
        self.fqdn_reverse_dash = "-".join(reverse(fqdn_as_list))
        self.fqdn_no_app = ".".join(fqdn_as_list[1:])
        self.fqdn_no_app_reverse = ".".join(reverse(fqdn_as_list[1:]))
        self.fqdn_no_app_reverse_dash = "-".join(reverse(fqdn_as_list[1:]))
        self.fqdn_no_env = ".".join(fqdn_as_list[2:])
        self.fqdn_no_env_reverse = ".".join(reverse(fqdn_as_list[2:]))
        self.fqdn_no_env_reverse_dash = "-".join(reverse(fqdn_as_list[2:]))
        self.environment_domain_name = ".".join(fqdn_as_list[1:])

        self.web_acl_name = "IPWhiteListWebACL"
        self.aws_role_arn = f"arn:aws:iam::{accounts.terraform_state_account_id}:role/{config.app_name}-terraform-pipleine-CodeBuildRole"

        self.aws_profile = f"{accounts.aws_account_id}_AWSPowerUserAccess"
        self.build_account_profile = f"{accounts.build_account_id}_AWSPowerUserAccess"
        self.dns_account_profile = f"{accounts.dns_account_id}_NetworkAdministrator"

        self.artifacts_bucket_name = f"{config.tldn}.{environment}.artifacts"
        self.destination_builds_bucket_name = f"{config.tldn}.{environment}.builds"
        self.source_build_bucket_name = f"{config.tldn}.{accounts.build_account_name}.builds"
        self.cloudtrails_logs_bucket_name = f"{config.tldn}.{environment}.cloudtrails.logs"
        self.terraform_bucket_name = f"{config.tldn}.{accounts.terraform_state_account_name}.terraform"
        self.aws_sns_topic_env_build_notification_name = f"{self.fqdn_no_app_reverse_dash}-build-notifications"
        self.aws_sns_topic_build_notification_name = f"{self.fqdn_no_env_reverse_dash}-build-notifications"
        self.terraform_dynamodb_table = f"{config.tldn}.{accounts.terraform_state_account_name}.terraform.lock"
        self.destination_builds_bucket_name = f"{config.tldn}.{environment}.builds"

    def get_fqdn_as_list(self, config, environment):
        fqdn_as_list = None
        tldn_as_list = config.tldn.split(".")[::-1]
        if environment == "prod":
            fqdn_as_list = [config.app_name] + tldn_as_list
        else:
            fqdn_as_list = [config.app_name, environment] + tldn_as_list

        fqdn_as_list = compact(fqdn_as_list)
        return fqdn_as_list


def reverse(str_list):
    return list(reversed(str_list))


def compact(str_list):
    return list(filter(None, str_list))
