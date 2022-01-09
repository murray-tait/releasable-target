import boto3


class Accounts():

    def __init__(self, environment, accounts_profile):
        super().__init__()

        self._accounts_profile = accounts_profile

        locals = self._get_locals_from_account_tags(environment)
        self.aws_account_id = locals.get("aws_account_id")
        self.dns_account_id = locals.get("dns_account_id")
        self.build_account_id = locals.get("build_account_id")
        self.build_account_name = locals.get("build_account_name")
        self.terraform_state_account_name = locals.get(
            "terraform_state_account_name")
        self.terraform_state_account_id = locals.get(
            "terraform_state_account_id")

    def _get_locals_from_account_tags(self, environment):
        accounts, account_ids = self.get_account_ids()

        locals = {}
        locals["terraform_state_account_name"] = "build"
        locals["terraform_state_account_id"] = account_ids["build"]

        for account in accounts:
            account_name = account['Name']
            account_id = account['Id']

            if account_name == environment:
                locals["aws_account_id"] = account_id

            tags = self.get_client().list_tags_for_resource(ResourceId=account_id)

            for tag in tags['Tags']:
                key = tag['Key'].replace('-', '_')
                value = tag['Value']
                children_key = key + '_children_account_ids'
                local_account_id_key = key + '_account_id'
                local_account_name_key = key + "_account_name"

                if value == environment:
                    if children_key not in locals:
                        locals[children_key] = []
                    locals[children_key].append(account_id)

                if account_name == environment:
                    locals[local_account_id_key] = account_ids[value]
                    locals[local_account_name_key] = value

        return locals

    def get_account_ids(self):
        client = self.get_client()

        accounts = client.list_accounts()['Accounts']
        account_ids = {}
        for account in accounts:
            account_ids[account['Name']] = account['Id']

        return accounts, account_ids

    def get_client(self):
        session = boto3.Session(profile_name=self._accounts_profile)

        client = session.client('organizations')
        return client
