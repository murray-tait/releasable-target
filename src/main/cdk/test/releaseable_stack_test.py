
from mock import patch, PropertyMock
from cdktf import App

from cdk.releasable_stack import ReleasableStack


@patch("cdk.releasable_stack.Accounts")
@patch("cdk.releasable_stack.Config")
def test_happy_path(Config, Accounts):
    mock_config = Config.return_value
    type(mock_config).tldn = PropertyMock(return_value="env.example.com")
    type(mock_config).app_name = PropertyMock(return_value="app_name")
    type(mock_config).use_role_arn = PropertyMock(return_value=False)
    mock_config._get_environment.return_value = "env"

    mock_accounts = Accounts.return_value
    type(mock_accounts).terraform_state_account_name = PropertyMock(
        return_value="terraform_state_account_name")
    type(mock_accounts).terraform_state_account_id = PropertyMock(
        return_value="terraform_state_account_id")
    type(mock_accounts).aws_account_id = PropertyMock(
        return_value="build_account_id")
    type(mock_accounts).build_account_id = PropertyMock(
        return_value="build_account_id")
    type(mock_accounts).build_account_name = PropertyMock(
        return_value="build_account_name")
    type(mock_accounts).dns_account_id = PropertyMock(
        return_value="build_account_id")

    app = App()
    stack = ReleasableStack(app, "release")
    app.synth()

    assert stack is not None
