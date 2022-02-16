#!/usr/bin/env python
import os

from cdktf_cdktf_provider_aws.acm import DataAwsAcmCertificate
from constructs import Construct
from cdktf import S3Backend


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
