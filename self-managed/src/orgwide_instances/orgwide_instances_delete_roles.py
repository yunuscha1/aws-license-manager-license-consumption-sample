from orgwide_instances_utils import *


def delete_stack_set(account_id):
    cf_client = get_cf_client(inputs["default_region"])

    caller = check_if_delegated_admin()

    try:
        cf_response = cf_client.delete_stack_instances(StackSetName=inputs["stack_set_name"],
                                                       DeploymentTargets=get_deployment_targets(inputs["ou_ids"],
                                                                              inputs["accounts"],
                                                                              "deletion"),
                                                       Regions=[inputs["default_region"]],
                                                       RetainStacks=False,
                                                       CallAs=caller
                                                       )
        if not polling(caller, cf_client, cf_response["OperationId"], inputs["stack_set_name"]):
            print("Error in deleting stack instances")
            exit()
    except Exception as Argument:
        print(str(Argument))

    print("Deleting Stack Set in management account")
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
