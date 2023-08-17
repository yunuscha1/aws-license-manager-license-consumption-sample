from orgwide_instances_utils import *


def enable_stack_set_service():
    client = get_cf_client(inputs["default_region"])
    client.activate_organizations_access()
    return


def get_stack_set_document(account_id):
    document = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Stack set template for Org Wide instance data aggregator",
        "Resources": {
            inputs["org_wide_instance_role_name"]: {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": inputs["org_wide_instance_role_name"],
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [{
                            "Effect": "Allow",
                            "Principal": {"AWS": account_id},
                            "Action": ["sts:AssumeRole"]
                        }]
                    },
                    "Policies": [{
                        "PolicyName": "OrgWideInstance",
                        "PolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [{
                                "Effect": "Allow",
                                "Action": ["ec2:DescribeInstances",
                                           "ec2:DescribeRegions",
                                           "ssm:DescribeInstanceInformation"],
                                "Resource": "*"
                            }]
                        }
                    }]
                }
            }
        }
    }
    return json.dumps(document)


def create_stack_set(account_id):
    cf_client = get_cf_client(default_region)
    orgs_client = get_org_client()
    caller = check_if_delegated_admin()
    print("Creating Stack Set in account: " + account_id)
    cf_response = cf_client.create_stack_set(StackSetName=inputs["stack_set_name"],
                                             TemplateBody=get_stack_set_document(account_id),
                                             PermissionModel="SERVICE_MANAGED",
                                             AutoDeployment={
                                                 "Enabled": True,
                                                 "RetainStacksOnAccountRemoval": False
                                             },
                                             CallAs=caller,
                                             Capabilities=["CAPABILITY_NAMED_IAM"])

    orgs_response = orgs_client.list_roots()

    print("Deploying stack instances in following OU Ids: ")
    for root in orgs_response["Roots"]:
        print(root["Id"])
    cf_response = cf_client.create_stack_instances(StackSetName=cf_response["StackSetId"],
                                     DeploymentTargets={
                                         "Accounts": ["438133634613", "360529614548"],  # TODO: Remove this line after done testing
                                         "OrganizationalUnitIds": [root["Id"] for root in orgs_response["Roots"]],
                                         "AccountFilterType": "INTERSECTION"
                                         # TODO: Remove this line after done testing
                                     },
                                     CallAs=caller,
                                     Regions=[inputs["default_region"]]
                                     )

    if not polling(caller, cf_client, cf_response["OperationId"]):
        print("Failure in stack instance creation")
        exit()


def main(command_line=None):
    print("Creating roles and policies throughout member accounts")

    global inputs
    inputs = get_inputs()

    manager_account_id = get_current_account_id()

    enable_stack_set_service()

    create_stack_set(manager_account_id)

    print("Successfully created roles in member accounts with the following template:")
    print(get_stack_set_document(manager_account_id))


if __name__ == '__main__':
    main()
