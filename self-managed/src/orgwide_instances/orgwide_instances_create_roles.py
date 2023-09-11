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
            inputs["org_wide_role_name"]: {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": inputs["org_wide_role_name"],
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


def get_deployment_targets():
    orgs_client = get_org_client()
    orgs_response = orgs_client.list_roots()
    ou_ids = [root["Id"] for root in orgs_response["Roots"]]
    if len(inputs['accounts']) == 0 and len(inputs['ou_ids']) == 0:
        print("Deploying stack instances in following OU Ids: ")
        for root in orgs_response["Roots"]:
            print(root["Id"])
        return {"OrganizationalUnitIds": ou_ids}
    deployment_targets = dict()
    if len(inputs['accounts']) > 0:
        deployment_targets["Accounts"] = inputs['accounts']
        deployment_targets["AccountFilterType"] = "INTERSECTION"
        print("Deploying stack instances in following accounts: ")
        for account in inputs['accounts']:
            print(account)
    if len(inputs['ou_ids']) > 0:
        ou_ids = list(set(ou_ids).intersection(set(inputs["ou_ids"])))
        deployment_targets["AccountFilterType"] = "UNION"
        print("Deploying stack instances in following OU ids: ")
        for ou_id in inputs["ou_ids"]:
            print(ou_id)

    deployment_targets["OrganizationalUnitIds"] = ou_ids
    return deployment_targets


def create_stack_set(account_id):
    cf_client = get_cf_client(inputs['default_region'])

    caller = check_if_delegated_admin()
    print("Creating Stack Set in management account")
    try:
        cf_response = cf_client.create_stack_set(StackSetName=inputs["stack_set_name"],
                                                 TemplateBody=get_stack_set_document(account_id),
                                                 PermissionModel="SERVICE_MANAGED",
                                                 AutoDeployment={
                                                     "Enabled": True,
                                                     "RetainStacksOnAccountRemoval": False
                                                 },
                                                 CallAs=caller,
                                                 Capabilities=["CAPABILITY_NAMED_IAM"])
    except Exception as Argument:
        if Argument.response['Error']['Code'] == 'NameAlreadyExistsException':
            print(inputs["stack_set_name"] + " already present in management account")
    cf_response = cf_client.create_stack_instances(StackSetName=inputs["stack_set_name"],
                                     DeploymentTargets=get_deployment_targets(),
                                     CallAs=caller,
                                     Regions=[inputs["default_region"]]
                                     )

    if not polling(caller, cf_client, cf_response["OperationId"], inputs['stack_set_name']):
        print("Failure in stack instance creation")
        exit()


def main(command_line=None):
    print("Creating roles and policies throughout member accounts")

    global inputs
    inputs = get_inputs()

    manager_account_id = get_current_account_id()

    caller = check_if_delegated_admin()

    if caller == 'SELF':
        enable_stack_set_service()

    create_stack_set(manager_account_id)

    print("Successfully created roles in member accounts with the following template:")
    print(get_stack_set_document(manager_account_id))


if __name__ == '__main__':
    main()
