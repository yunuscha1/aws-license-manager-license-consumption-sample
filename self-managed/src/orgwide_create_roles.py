import boto3
import json

# Inputs
default_region = "us-east-1"
ou_ids = ["r-229p"]  # Insert AWS Organizations Org-Id
manager_account_id = "360529614548"  # Insert manager account ID
report_path_and_filename = "roles_report.txt"
org_wide_instance_role_name = "ManagerAccountEC2DescribeInstances"


def enable_stack_set_service():
    try:
        client = get_cf_client(default_region)
        response = client.activate_organizations_access()
    except Exception as Argument:
        msgs = ["Could not enable stack set service role in the following account: " + manager_account_id,
                "For more information, go here: "
                "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-activate-trusted-access.html"]
        write_report(Argument, msgs)
        exit()


def get_stack_set_document():
    document = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Insert description here",
        "Resources": {
            org_wide_instance_role_name: {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": org_wide_instance_role_name,
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [{
                            "Effect": "Allow",
                            "Principal": {"AWS": "arn:aws:iam::" + manager_account_id + ":root"},
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


def create_stack_set():
    client = get_cf_client(default_region)
    try:

        response = client.create_stack_set(StackSetName="OrgWideInstanceStackSet",
                                           TemplateBody=get_stack_set_document(),
                                           PermissionModel="SERVICE_MANAGED",
                                           AutoDeployment={
                                               "Enabled": True,
                                               "RetainStacksOnAccountRemoval": False
                                           },
                                           Capabilities=["CAPABILITY_NAMED_IAM"])

        print(response["StackSetId"])
        client.create_stack_instances(StackSetName=response["StackSetId"],
                                     DeploymentTargets={
                                         "Accounts": ["438133634613"],
                                         "OrganizationalUnitIds": ou_ids,
                                         "AccountFilterType": "INTERSECTION"
                                     },
                                     Regions=[default_region]
                                     )

    except Exception as Argument:
        msgs = ["Could not create stack: " + manager_account_id,
                "For more information, go here: "
                "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-activate-trusted-access.html"]
        write_report(Argument, msgs)
        exit()


def get_org_wide_instance_role():
    role_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "AWS": "arn:aws:iam::" + manager_account_id + ":root"
                },
                "Action": "sts:AssumeRole",
                "Condition": {}
            }
        ]
    }
    return json.dumps(role_document)


def create_roles_and_policies(accounts):
    for account in accounts:
        sts_response = sts_assume_role(account)
        if sts_response is None:
            continue
        try:
            # Implement this function to delete any existing roles and policies
            # delete_roles_and_policies()
            client = get_iam_client(sts_response["Credentials"]["AccessKeyId"],
                                    sts_response["Credentials"]["SecretAccessKey"],
                                    sts_response["Credentials"]["SessionToken"])

            role_response = client.create_role(RoleName=org_wide_instance_role_name,
                                               AssumeRolePolicyDocument=get_org_wide_instance_role())

            policy_response = client.create_policy(PolicyName='OrgWideInstances',
                                                   PolicyDocument=get_org_wide_instance_policy())

            print(role_response["RoleName"])
            print(policy_response["Arn"])
            client.attach_role_policy(RoleName=role_response["Role"]["RoleName"],
                                      PolicyArn=policy_response["Arn"])

        except Exception as Argument:
            msgs = ["Failed policy/role creation in the following account: " + account,
                    "Make sure that " + role_name + " has admin privileges in the account!"]
            write_report(Argument, msgs)


def write_report(argument, msgs):
    report_fp = open(report_path_and_filename, "a")
    report_fp.write(str(argument) + '\n')
    for msg in msgs:
        report_fp.write(msg + '\n')
    report_fp.close()


def get_org_client():
    return boto3.client(service_name='organizations')


def get_cf_client(region):
    return boto3.client(service_name='cloudformation',
                        region_name=region)


# def get_sts_client():
#     return boto3.client(service_name='sts')


# def get_iam_client(access_key, secret_key, session_token):
#     return boto3.client(service_name='iam',
#                         aws_access_key_id=access_key,
#                         aws_secret_access_key=secret_key,
#                         aws_session_token=session_token)


def main(command_line=None):
    print("Start of creating roles and policies throughout organization")

    print("Creating a new report file for stack set creation")
    report_fp = open(report_path_and_filename, "w")
    report_fp.close()

    enable_stack_set_service()

    create_stack_set()


if __name__ == '__main__':
    main()
