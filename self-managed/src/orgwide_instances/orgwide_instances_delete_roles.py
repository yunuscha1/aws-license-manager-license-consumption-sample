from orgwide_instances_utils import *


def delete_stack_set(account_id):
    cf_client = get_cf_client(inputs["default_region"])
    orgs_client = get_org_client()
    orgs_response = orgs_client.list_roots()

    print("Deleting stack instances in following OU Ids:")
    for root in orgs_response["Roots"]:
        print(root["Id"])

    caller = check_if_delegated_admin()
    cf_response = cf_client.delete_stack_instances(StackSetName=inputs["stack_set_name"],
                                                   DeploymentTargets={
                                                       "Accounts": ["438133634613", "360529614548"],
                                                       # TODO: Remove this line after done testing
                                                       "OrganizationalUnitIds": [root["Id"] for root in
                                                                                 orgs_response["Roots"]],
                                                       "AccountFilterType": "INTERSECTION"
                                                       # TODO: Remove this line after done testing
                                                   },
                                                   Regions=[inputs["default_region"]],
                                                   RetainStacks=False,
                                                   CallAs=caller
                                                   )

    if not polling(caller, cf_client, cf_response["OperationId"], inputs["stack_set_name"]):
        print("Error in deleting stack instances")
        exit()

    print("Deleting Stack Set in account: " + account_id)
    cf_client.delete_stack_set(StackSetName=inputs["stack_set_name"], CallAs=caller)


def main(command_line=None):
    print("Deleting roles and policies throughout member accounts")

    global inputs
    inputs = get_inputs()

    manager_account_id = get_current_account_id()

    delete_stack_set(manager_account_id)

    print("Successfully deleted all roles and permissions in member accounts")


if __name__ == '__main__':
    main()
