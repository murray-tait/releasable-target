import json
import boto3
import os

APPLICATION_NAME = os.environ["APPLICATION_NAME"]
BRANCH_NAME = os.environ["BRANCH_NAME"]
FUNCTION_NAMES = os.environ["FUNCTION_NAMES"].split(",")

if APPLICATION_NAME == "":
    raise Exception("$APPLICATION_NAME must be set")

if BRANCH_NAME == "":
    raise Exception("$BRANCH_NAME must be set")

if len(FUNCTION_NAMES) == 0:
    raise Exception("$FUNCTION_NAMES must be set")


def updater(event, context):
    print("Handling event: {}".format(json.dumps(event, sort_keys=True)))

    if "Records" not in event:
        print("No Update records found. Skipping")
        return

    for record in event["Records"]:
        actual_event = json.loads(record["Sns"]["Message"])

        if "Records" not in actual_event:
            print("No update records found. Skipping")
            continue

        process_record(actual_event["Records"][0])


def process_record(record):
    bucket = record["s3"]["bucket"]["name"]
    key = record["s3"]["object"]["key"]
    print("Checking {}/{}".format(bucket, key))

    if we_should_care(key):
        update_lambda(bucket, key)
    else:
        print("ignoring")


def update_lambda(bucket, key):
    client = boto3.client("lambda")

    for function in FUNCTION_NAMES:
        print("Updating {}".format(function))

        client.update_function_code(FunctionName=function, S3Bucket=bucket, S3Key=key)


def we_should_care(key):
    path = "builds/{}/refs/heads/{}/lambda.zip".format(APPLICATION_NAME, BRANCH_NAME)
    return key == path
