import boto3
import csv
import json

# Inputs
default_regions = ['us-east-1']  # insert desired regions into the list
output_path = ""  # insert desired output path; default is pwd
report_filename = "instances_report.txt"  # insert desired report name
role_name = "ManagerAccountEC2DescribeInstances"  # insert chosen role name; this role should be located
# managed accounts and have "ec2:describeInstances" and "ssm:describeInstanceInformation" permission. Additionally,
# the manager account should have permissions to assume this role. More information can be found here
# https://aws.amazon.com/blogs/security/how-to-use-trust-policies-with-iam-roles/

default_fields = {"InstanceId", "UsageOperation", "ProductCodes", "PlatformName", "PlatformType", "PlatformVersion"}
categorized_fields = {
    "license_included": {"InstanceId", "UsageOperation"},
    "marketplace": {"InstanceId", "UsageOperation", "ProductCodes"},
    "byol": {"InstanceId", "UsageOperation", "PlatformName", "PlatformType", "PlatformVersion"}
}


def list_all_accounts():
    org_client = get_org_client()
    response = org_client.list_accounts()
    all_accounts = []

    for account in response["Accounts"]:
        all_accounts.append(account["Id"])

    while "NextToken" in response:
        response = org_client.list_accounts(NextToken=response["NextToken"])
        for account in response["Accounts"]:
            all_accounts.append(account["Id"])

    return all_accounts


def categorize_ec2_instances(all_accounts):
    categorized_ec2 = {"license_included": [], "byol": [], "marketplace": []}

    # Loading in billing codes
    f = open('billing_codes.json')
    billing_codes = json.load(f)
    f.close()

    # Loading in product codes
    f = open('product_codes.json')
    product_codes = json.load(f)
    f.close()
    all_product_codes = []
    for value in product_codes.values():
        all_product_codes += value

    for account in all_accounts:
        sts_response = sts_assume_role(account)
        if sts_response is None:
            continue
        for region in default_regions:
            byol = []
            ec2_instances = fetch_ec2_instances(account, region, sts_response)
            for ec2_instance in ec2_instances:
                if any([product_code["ProductCodeId"] in all_product_codes for product_code in
                          ec2_instance["ProductCodes"]]):
                    categorized_ec2["marketplace"].append(format_data(ec2_instance, False))
                elif ec2_instance["UsageOperation"] in billing_codes["license_included"]:
                    categorized_ec2["license_included"].append(format_data(ec2_instance, False))
                else:
                    byol.append(ec2_instance)
            categorized_ec2["byol"] += get_ec2_instance_information(
                account, byol, region, sts_response)
    return categorized_ec2


def fetch_ec2_instances(account, region, sts_response):
    try:
        ec2_client = get_ec2_client(sts_response["Credentials"]["AccessKeyId"],
                                    sts_response["Credentials"]["SecretAccessKey"],
                                    sts_response["Credentials"]["SessionToken"],
                                    region)

        response = ec2_client.describe_instances()

        ec2_instances = []
        for reservation in response["Reservations"]:
            ec2_instances += reservation["Instances"]

        while "NextToken" in response:
            response = ec2_client.describe_instances(NextToken=response["NextToken"])
            for reservation in response["Reservations"]:
                ec2_instances += reservation["Instances"]

    except Exception as Argument:
        msgs = ["Failed ec2 describeInstances in the following account: " + account,
                "Make sure that the assumed role has permission for ec2:describeInstances"]
        write_report(Argument, msgs)
        return []
    return ec2_instances


def get_ec2_instance_information(account, ec2_instances, sts_response, region):
    try:
        ssm_client = get_ssm_client(sts_response["Credentials"]["AccessKeyId"],
                                    sts_response["Credentials"]["SecretAccessKey"],
                                    sts_response["Credentials"]["SessionToken"],
                                    region)

        ec2_instance_mapping = {ec2_instance["InstanceId"]: ec2_instance for ec2_instance in ec2_instances}

        ec2_instance_information_list = []
        response = ssm_client.describe_instance_information(Filter={"InstanceIds": ec2_instance_mapping.keys()})
        ec2_instance_information_list += response["InstanceInformationList"]

        while "NextToken" in response:
            response = ssm_client.describe_instance_information(NextToken=response["NextToken"])
            ec2_instance_information_list += response["InstanceInformationList"]

    except Exception as Argument:
        msgs = ["Failed SSM describeInstanceInformation in the following account: " + account,
                "Make sure that the assumed role has permission for ssm:describeInstanceInformation"]
        write_report(Argument, msgs)
        return []

    # Filter SSM Describe Instance Information
    instance_information_keys = ["PlatformName", "PlatformType", "PlatformVersion"]
    for ec2_instance_information in ec2_instance_information_list:
        for key in instance_information_keys:
            ec2_instance_mapping[ec2_instance_information["InstanceId"]][key] = ec2_instance_information[key]
    return [format_data(ec2_instance, True) for ec2_instance in ec2_instance_mapping.values()]


# Alter desired keys to filter ec2 instance information
# Change to "return ec2_instance" if no filters are desired
def format_data(ec2_instance, byol):
    if byol:
        desired_fields = default_fields.copy() + ["PlatformName", "PlatformType", "PlatformVersion"]
    else:
        desired_fields = default_fields.copy()
    for key in desired_fields.copy():
        if ec2_instance.get(key) is None or ec2_instance.get(key) == []:
            desired_fields.remove(key)
    return {key: ec2_instance.get(key) for key in desired_fields}


def sts_assume_role(account):
    sts_client = get_sts_client()
    role_arn = "arn:aws:iam::" + account + ":role/" + role_name
    try:
        sts_response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="ManagerAccountEC2DescribeInstances",
        )
    except Exception as Argument:
        msgs = ["Could not assume " + role_name + " role in the following account: " + account,
                "Check for typos in role name or permissions in the account"]
        write_report(Argument, msgs)
        return None
    return sts_response


def output_csv_helper(ec2_instance, key):
    return [ec2_instance.get(field) for field in categorized_fields[key]]


def output_csv(categorized_ec2_instances):
    for key, value in categorized_ec2_instances.items():
        with open(key+".csv", 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(categorized_fields[key])
            for ec2_instance in value:
                writer.writerow(output_csv_helper(ec2_instance, key))


def write_report(argument, msgs):
    report_fp = open(output_path + report_filename, "a")
    if argument is not None:
        report_fp.write(str(argument) + '\n')
    for msg in msgs:
        report_fp.write(msg + '\n')
    report_fp.close()


def log_totals(categorized_ec2_instances):
    msgs = ["Total instances: " + str(len(categorized_ec2_instances.values())) + "\n",
            "License Included: " + str(len(categorized_ec2_instances["license_included"])) + "\n"
            "BYOL: " + str(len(categorized_ec2_instances["byol"])) + "\n"
            "Marketplace: " + str(len(categorized_ec2_instances["marketplace"])) + "\n"]
    write_report(None, msgs)


def get_org_client():
    return boto3.client(service_name='organizations')


def get_sts_client():
    return boto3.client(service_name='sts')


def get_ec2_client(access_key, secret_key, session_token, region):
    return boto3.client(service_name='ec2',
                        aws_access_key_id=access_key,
                        aws_secret_access_key=secret_key,
                        aws_session_token=session_token,
                        region_name=region)


def get_ssm_client(access_key, secret_key, session_token, region):
    return boto3.client(service_name='ssm',
                        aws_access_key_id=access_key,
                        aws_secret_access_key=secret_key,
                        aws_session_token=session_token,
                        region_name=region)


def main(command_line=None):
    print("Start of the orgWide describe instances sample model")

    print("Creating a new report file")
    report_fp = open(output_path + report_filename, "w")
    report_fp.close()

    all_accounts = list_all_accounts()

    categorized_ec2_instances = categorize_ec2_instances(all_accounts)

    output_csv(categorized_ec2_instances)

    log_totals(categorized_ec2_instances)


if __name__ == '__main__':
    main()
