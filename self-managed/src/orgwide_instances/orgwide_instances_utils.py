import boto3
import time
import json

# Constants
TOTAL = "total"
LICENSE_INCLUDED = "license_included"
MARKETPLACE = "marketplace"
BYOL = "byol"
TOTAL_ERRORS = "total_errors"
STS_ERRORS = "sts_errors"
EC2_ERRORS = "ec2_errors"
SSM_ERRORS = "ssm_errors"
STS_ERROR_MESSAGES = "sts_error_messages"
EC2_ERROR_MESSAGES = "ec2_error_messages"
SSM_ERROR_MESSAGES = "ssm_error_messages"

categorized_fields = {
    LICENSE_INCLUDED: {"AccountId", "PlatformDetails", "InstanceId", "Region"},
    MARKETPLACE: {"AccountId", "PlatformDetails", "InstanceId", "ProductCodes", "Region"},
    BYOL: {"AccountId", "InstanceId", "PlatformDetails", "PlatformName", "PlatformType", "PlatformVersion", "Region"}
}


def get_current_account_id():
    sts_client = get_sts_client()
    sts_response = sts_client.get_caller_identity()
    return sts_response["Account"]


def check_if_delegated_admin():
    current_account = get_current_account_id()

    org_client = get_org_client()
    org_response = org_client.list_delegated_administrators()

    if any([current_account == da["Id"] for da in org_response["DelegatedAdministrators"]]):
        return 'DELEGATED_ADMIN'
    return 'SELF'


def polling(caller, cf_client, operation_id, stack_set_name):
    cf_response = cf_client.describe_stack_set_operation(StackSetName=stack_set_name,
                                                         OperationId=operation_id,
                                                         CallAs=caller)
    while (cf_response["StackSetOperation"]["Status"] == 'QUEUED' or
           cf_response["StackSetOperation"]["Status"] == 'RUNNING'):
        time.sleep(10)
        cf_response = cf_client.describe_stack_set_operation(StackSetName=stack_set_name,
                                                             OperationId=operation_id,
                                                             CallAs=caller)
    if cf_response["StackSetOperation"]["Status"] != 'SUCCEEDED':
        return False
    return True


def get_inputs():
    with open("orgwide_instances_inputs.json") as fp:
        return json.load(fp)


def get_org_client():
    return boto3.client(service_name='organizations')


def get_cf_client(region):
    return boto3.client(service_name='cloudformation',
                        region_name=region)


def get_sts_client():
    return boto3.client(service_name='sts')


# Inputs
source_regions = []
default_region = "us-east-1"
stack_set_name = "OrgWideInstanceAggregatorStackSet"  # If using stackset creation
org_wide_instance_role_name = "AdminOrgWideInstancesAggregator"  # insert chosen role name; this role should be located
# managed accounts and have "ec2:describeInstances" and "ssm:describeInstanceInformation" permission. Additionally,
# the manager account should have permissions to assume this role. More information can be found here
# https://aws.amazon.com/blogs/security/how-to-use-trust-policies-with-iam-roles/

