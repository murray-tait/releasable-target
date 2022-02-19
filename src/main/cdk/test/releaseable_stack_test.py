from mock import patch, PropertyMock, Mock
from cdktf import App

from cdk.releasable_stack import ReleasableStack
from jsii._kernel.providers.process import InvokeResponse
from jsii._kernel.providers.process import CreateRequest
import jsii


@patch("cdk.releasable_stack.get_environment")
@patch("cdk.releasable_stack.Accounts")
@patch("cdk.releasable_stack.Config")
@patch("cdk.env.prepare_zip")
# @patch("jsii._kernel.providers.process.ProcessProvider.invoke")
def test_happy_path(prepare_zip, Config, Accounts, get_environment):
    # Arrange

    mock_config = Config.return_value
    provider = jsii.kernel.provider
    mock_provider = Mock(wraps=provider)
    jsii.kernel.provider = mock_provider

    type(mock_config).tldn = PropertyMock(return_value="env.example.com")
    type(mock_config).app_name = PropertyMock(return_value="app_name")
    type(mock_config).aws_region = PropertyMock(return_value="eu-west-1")
    type(mock_config).use_role_arn = PropertyMock(return_value=False)
    get_environment.return_value = "env"

    mock_accounts = Accounts.return_value
    type(mock_accounts).terraform_state_account_name = PropertyMock(
        return_value="terraform_state_account_name"
    )
    type(mock_accounts).terraform_state_account_id = PropertyMock(
        return_value="terraform_state_account_id"
    )
    type(mock_accounts).aws_account_id = PropertyMock(return_value="build_account_id")
    type(mock_accounts).build_account_id = PropertyMock(return_value="build_account_id")
    type(mock_accounts).build_account_name = PropertyMock(
        return_value="build_account_name"
    )
    type(mock_accounts).dns_account_id = PropertyMock(return_value="build_account_id")
    #    invoke.return_value = InvokeResponse(result=None)

    prepare_zip.return_value = "abcdf"

    app = App()

    # Action
    ReleasableStack(app, "release")

    # Assert
    mock_provider.create.mock_calls[1].args[0].fqn == "cdktf.TerraformStack"
    mock_provider.create.mock_calls[1].args[0].args[0] == app
    mock_provider.create.mock_calls[1].args[0].args[1] == "release"
    mock_provider.create.assert_any_call(
        CreateRequest(
            fqn="cdktf.TerraformStack",
            args=[app, "release"],
            overrides=[],
            interfaces=["constructs.IConstruct"],
        )
    )
