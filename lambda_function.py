import boto3
import json
import os
from datetime import datetime

ec2 = boto3.client("ec2")
sns = boto3.client("sns")
s3 = boto3.client("s3")

def lambda_handler(event, context):
    bucket_name = os.environ["REPORT_BUCKET"]
    sns_topic = os.environ["SNS_TOPIC_ARN"]

    findings = []

    # 1️⃣ Public IPAM Insights
    ipam = boto3.client("ec2")
    ipam_data = ipam.get_ipam_resource_cidrs(
        Filters=[{"Name": "resource-public-ip", "Values": ["true"]}]
    )
    findings.extend(ipam_data.get("IpamResourceCidrs", []))

    # 2️⃣ Network Access Analyzer placeholder
    # For simplicity, simulate findings
    naa_findings = [
        {"ResourceId": "eni-1234567890abcdef", "Issue": "Publicly accessible ENI"}
    ]
    findings.extend(naa_findings)

    # Store report in S3
    report_key = f"public_exposure_report_{datetime.utcnow().isoformat()}.json"
    s3.put_object(
        Bucket=bucket_name,
        Key=report_key,
        Body=json.dumps(findings, indent=2),
        ContentType="application/json"
    )

    # Send SNS notification
    sns.publish(
        TopicArn=sns_topic,
        Subject="Public Exposure Findings",
        Message=f"{len(findings)} public exposure issues found. Report stored at s3://{bucket_name}/{report_key}"
    )

    return {"statusCode": 200, "body": json.dumps({"findings": findings})}