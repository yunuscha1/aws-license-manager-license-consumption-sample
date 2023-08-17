import importlib.util
import subprocess
import sys
import json


def main(command_line=None):

    if importlib.util.find_spec('boto3') is None:
        print("boto3 is not installed")
        print("Installing boto3")
        subprocess.call([sys.executable, '-m', 'pip', 'install', 'boto3'])

    try:
        import boto3
    except ImportError:
        print("Error importing boto3")
        exit()

    with open("orgwide_instances_inputs.json") as fp:
        inputs = json.load(fp)

    if inputs["automatic_member_role_creation"]:
        print("Automatic member role creation is ON")
        cf_client = boto3.client(service_name='cloudformation',
                                 region_name=inputs["default_region"])
        response = cf_client.list_stack_sets()

        print("Checking if necessary stack set is present in management account")
        if not any([inputs["stack_set_name"] == stack_set["StackSetName"] and "ACTIVE" == stack_set["Status"]
                    for stack_set in response["Summaries"]]):
            subprocess.call(["python3", "orgwide_instances_create_roles.py"])
    else:
        print("Automatic member role creation is OFF")
        print("Ensure that " + inputs["org_wide_role_name"] + " is present in member accounts with correct permissions")
    subprocess.call(["python3", "orgwide_instances_data_aggregator.py"])


if __name__ == '__main__':
    main()