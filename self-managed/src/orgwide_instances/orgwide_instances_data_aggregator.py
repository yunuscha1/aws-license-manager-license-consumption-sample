import csv
from orgwide_instances_utils import *

summary = dict()
error_messages = dict()
misconfigured_accounts = set()


def check_stack_set_status():
    cf_client = get_cf_client(inputs['default_region'])
    caller = check_if_delegated_admin()
    response = cf_client.detect_stack_set_drift(StackSetName=inputs["stack_set_name"],
                                                CallAs=caller)
    operation_id = response["OperationId"]
    response = cf_client.describe_stack_set_operation(StackSetName=inputs["stack_set_name"],
                                                      OperationId=operation_id,
                                                      CallAs=caller)
    while response["StackSetOperation"]["Status"] == "RUNNING" or response["StackSetOperation"]["Status"] == "QUEUED":
        print("Polling to see if necessary roles and permissions are present in member accounts")
        time.sleep(10)
        response = cf_client.describe_stack_set_operation(StackSetName=inputs["stack_set_name"],
                                                          OperationId=operation_id,
                                                          CallAs=caller)
    misconfigured_stacks = 0
    for account in list_all_accounts():
        try:
            dsi_response = cf_client.describe_stack_instance(
                StackSetName=inputs["stack_set_name"],
                StackInstanceAccount=account,
                StackInstanceRegion=inputs["default_region"],
                CallAs= caller
            )
            if dsi_response["StackInstance"]["DriftStatus"] != "IN_SYNC":
                misconfigured_stacks += 1
                summary[account][STS_ERRORS] += 1
                error_messages[account][STS_ERROR_MESSAGES].append("Potentially incorrect stack instance for "
                                                                   "roles and permissions")
        except Exception as Argument:
            misconfigured_stacks += 1

    if misconfigured_stacks > 0:
        print("WARNING - Number of potentially misconfigured accounts: " + str(misconfigured_stacks))


def list_all_accounts():
    org_client = get_org_client()
    if len(inputs['accounts']) == 0 and len(inputs['ou_ids']) == 0:
        response = org_client.list_accounts()
        all_accounts = []

        for account in response["Accounts"]:
            all_accounts.append(account["Id"])

        while "NextToken" in response:
            response = org_client.list_accounts(NextToken=response["NextToken"])
            for account in response["Accounts"]:
                all_accounts.append(account["Id"])

        return all_accounts
    all_accounts = inputs['accounts']
    for ou_id in inputs['ou_ids']:
        response = org_client.list_accounts_for_parent(ParentId=ou_id)
        for account in response["Accounts"]:
            all_accounts.append(account["Id"])

        while "NextToken" in response:
            response = org_client.list_accounts_for_parent(ParentId=ou_id, NextToken=response["NextToken"])
            for account in response["Accounts"]:
                all_accounts.append(account["Id"])

    return list(set(all_accounts))


def get_license_included_map():
    with open("license_included_codes.json") as fp:
        return json.load(fp)


def get_billing_codes():
    # Loading in billing codes
    with open("billing_codes.json") as fp:
        return json.load(fp)


def get_product_codes():
    # Loading in product codes
    with open("product_codes.json") as fp:
        product_codes = json.load(fp)
        product_codes.update(inputs["custom_product_codes"])
        return [item for sublist in product_codes.values() for item in sublist], product_codes


def sts_assume_role(account):
    sts_client = get_sts_client()
    role_arn = "arn:aws:iam::" + account + ":role/" + inputs["org_wide_role_name"]
    try:
        sts_response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="AdminOrgWideInstancesAggregator",
        )
    except Exception as Argument:
        summary[account][STS_ERRORS] += 1
        error_messages[account][STS_ERROR_MESSAGES].append(str(Argument))
        return None
    return sts_response


def get_regions(account, sts_response):
    try:
        ec2_client = get_ec2_client(sts_response["Credentials"]["AccessKeyId"],
                                    sts_response["Credentials"]["SecretAccessKey"],
                                    sts_response["Credentials"]["SessionToken"],
                                    inputs["default_region"])
        response = ec2_client.describe_regions()
    except Exception as Argument:
        summary[account]["ec2_errors"] += 1
        error_messages[account]["ec2_error_messages"].append(inputs["default_region"] + ": " + str(Argument))
        if Argument.response['Error']['Code'] == 'UnauthorizedOperation':
            misconfigured_accounts.add(account)
        return []
    return [region["RegionName"] for region in response["Regions"]]


def format_data_helper(product_code_id, product_codes):
    for product_code_name, product_code_ids in product_codes.items():
        if product_code_id in product_code_ids:
            return product_code_name
    return "UNKNOWN"


def format_data(account_id, ec2_instance, instance_type, region, product_codes=None, license_included_map=None):
    desired_fields = categorized_fields[instance_type].copy()
    for key in desired_fields.copy():
        if ec2_instance.get(key) is None or ec2_instance.get(key) == []:
            desired_fields.remove(key)
    if instance_type == MARKETPLACE:
        ec2_instance["ProductCodes"] = ":".join([format_data_helper(product_code["ProductCodeId"], product_codes)
                                                 for product_code in ec2_instance["ProductCodes"]])
    if instance_type == LICENSE_INCLUDED:
        ec2_instance["LicenseIncludedType"] = license_included_map[ec2_instance["UsageOperation"]]
    output = {key: ec2_instance.get(key) for key in desired_fields}
    output["AccountId"] = account_id
    output["Region"] = region
    return output


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
        summary[account][EC2_ERRORS] += 1
        error_messages[account][EC2_ERROR_MESSAGES].append(region + ": " + str(Argument))
        if Argument.response['Error']['Code'] == 'UnauthorizedOperation':
            misconfigured_accounts.add(account)
        return []
    return ec2_instances


def initialize_summary():
    return {TOTAL: 0, LICENSE_INCLUDED: 0, MARKETPLACE: 0, BYOL: 0, TOTAL_ERRORS: 0, STS_ERRORS: 0, EC2_ERRORS: 0,
            SSM_ERRORS: 0}


def initialize_error_message():
    return {STS_ERROR_MESSAGES: [], EC2_ERROR_MESSAGES: [], SSM_ERROR_MESSAGES: []}


def categorize_ec2_instances(all_accounts):
    categorized_ec2 = {LICENSE_INCLUDED: [], BYOL: [], MARKETPLACE: []}
    license_included_map = get_license_included_map()
    all_billing_codes = get_billing_codes()
    all_product_codes, product_codes = get_product_codes()
    for account in all_accounts:
        sts_response = sts_assume_role(account)
        if sts_response is None:
            continue

        if inputs["source_regions"]:
            source_regions = inputs["source_regions"]
        else:
            source_regions = get_regions(account, sts_response)
        for region in source_regions:
            byol = []
            ec2_instances = fetch_ec2_instances(account, region, sts_response)
            for ec2_instance in ec2_instances:
                if len(ec2_instance["ProductCodes"]) > 0:
                    categorized_ec2[MARKETPLACE].append(format_data(account, ec2_instance, MARKETPLACE, region,
                                                                    product_codes=product_codes))
                    summary[account][MARKETPLACE] += 1
                elif ec2_instance["UsageOperation"] in all_billing_codes[LICENSE_INCLUDED]:
                    categorized_ec2[LICENSE_INCLUDED].append(format_data(account, ec2_instance, LICENSE_INCLUDED, region,
                                                                         license_included_map=license_included_map))
                    summary[account][LICENSE_INCLUDED] += 1
                else:
                    byol.append(ec2_instance)
                    summary[account][BYOL] += 1
            if byol:
                categorized_ec2[BYOL] += get_ec2_instance_information(
                    account, byol, region, sts_response)
    return categorized_ec2


def get_ec2_instance_information(account, ec2_instances, region, sts_response):
    try:
        ssm_client = get_ssm_client(sts_response["Credentials"]["AccessKeyId"],
                                    sts_response["Credentials"]["SecretAccessKey"],
                                    sts_response["Credentials"]["SessionToken"],
                                    region)
        ec2_instance_mapping = {ec2_instance["InstanceId"]: ec2_instance for ec2_instance in ec2_instances}
        ec2_instance_information_list = []
        response = ssm_client.describe_instance_information(Filters=[{
            "Key": "InstanceIds",
            "Values": [ec2_instance["InstanceId"] for ec2_instance in ec2_instances]
        }])
        ec2_instance_information_list += response["InstanceInformationList"]
        while "NextToken" in response:
            response = ssm_client.describe_instance_information(NextToken=response["NextToken"])
            ec2_instance_information_list += response["InstanceInformationList"]
    except Exception as Argument:
        summary[account][SSM_ERRORS] += 1
        error_messages[account][SSM_ERROR_MESSAGES].append(region + ": " + str(Argument))
        if Argument.response['Error']['Code'] == 'NotAuthorized':
            misconfigured_accounts.add(account)
        return []

    # Filter SSM Describe Instance Information
    instance_information_keys = ["PlatformName", "PlatformType", "PlatformVersion"]
    for ec2_instance_information in ec2_instance_information_list:
        for key in instance_information_keys:
            ec2_instance_mapping[ec2_instance_information["InstanceId"]][key] = ec2_instance_information[key]
    return [format_data(account, ec2_instance, BYOL, region) for ec2_instance in ec2_instance_mapping.values()]


def output_csv_helper(ec2_instance, key):
    return [ec2_instance.get(field) for field in categorized_fields[key]]


def output_csv(categorized_ec2_instances):
    for key, value in categorized_ec2_instances.items():
        with open(key + ".csv", 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(categorized_fields[key])
            for ec2_instance in value:
                writer.writerow(output_csv_helper(ec2_instance, key))


def get_iam_client(access_key, secret_key, session_token):
    return boto3.client(service_name='iam',
                        aws_access_key_id=access_key,
                        aws_secret_access_key=secret_key,
                        aws_session_token=session_token)


def get_ec2_client(access_key, secret_key, session_token, region=None):
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


def create_summary(all_accounts):
    with open("summary.csv", 'w', newline='') as file:
        writer = csv.writer(file)
        summary['ALL'] = initialize_summary()
        for key in summary['ALL'].keys():
            summary['ALL'][key] = sum([summary[account][key] for account in all_accounts])
        keys = ['ALL'] + all_accounts
        writer.writerow(["AccountId", TOTAL, LICENSE_INCLUDED, MARKETPLACE, BYOL, TOTAL_ERRORS, STS_ERRORS, EC2_ERRORS,
                         SSM_ERRORS])
        for key in keys:
            summary[key][TOTAL] = summary[key][LICENSE_INCLUDED] + summary[key][MARKETPLACE] + summary[key][BYOL]
            summary[key][TOTAL_ERRORS] = summary[key][STS_ERRORS] + summary[key][EC2_ERRORS] + summary[key][SSM_ERRORS]
            row = [value for value in summary[key].values()]
            row = [key] + row
            writer.writerow(row)


def write_report():
    with open("report.txt", "w") as report_fp:
        if len(misconfigured_accounts) != 0:
            report_fp.write("The following accounts are not provisioned the correct permissions: \n")
            for account in misconfigured_accounts:
                report_fp.write(account + '\n')
            report_fp.write('\n')
        if summary['ALL'][TOTAL_ERRORS] == 0:
            return
        report_fp.write("Errors are separated by AccountId and have the region of error origin listed \n \n")
        for account, categorized_messages in error_messages.items():
            if summary[account][TOTAL_ERRORS] == 0:
                continue
            report_fp.write(account + ":\n")
            for error_type, messages in categorized_messages.items():
                report_fp.write(error_type + "\n\n")
                for message in messages:
                    report_fp.write(message + "\n\n")
            report_fp.write("\n\n")


def main(command_line=None):
    print("Start of the Org Wide Instance Aggregator")

    global inputs
    inputs = get_inputs()

    all_accounts = list_all_accounts()
    print("Attempting to gather data from " + str(len(all_accounts)) + " accounts")

    for account in all_accounts:
        summary[account] = initialize_summary()
        error_messages[account] = initialize_error_message()

    if inputs["automatic_member_role_creation"] and inputs["check_stack_set_status"]:
        print("Checking stack set status")
        check_stack_set_status()

    categorized_ec2_instances = categorize_ec2_instances(all_accounts)

    print("Creating categorized CSVs")
    output_csv(categorized_ec2_instances)

    print("Creating a summary of findings")
    create_summary(all_accounts)

    print("Creating report")
    write_report()


if __name__ == '__main__':
    main()
