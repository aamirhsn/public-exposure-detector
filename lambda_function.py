import boto3
import json
import datetime
import os

def _is_bucket_public(s3_client, bucket_name):
    reasons = []
    is_public = False
    # Check ACL grants
    try:
        acl = s3_client.get_bucket_acl(Bucket=bucket_name)
        for grant in acl.get("Grants", []):
            grantee = grant.get("Grantee", {})
            uri = grantee.get("URI", "")
            if uri.endswith("/AllUsers") or uri.endswith("/AuthenticatedUsers"):
                is_public = True
                reasons.append("ACL grants to all users")
    except Exception as e:
        reasons.append(f"ACL check failed: {e}")

    # Check bucket policy for wildcard principal
    try:
        policy = s3_client.get_bucket_policy(Bucket=bucket_name)
        policy_text = policy.get("Policy", "")
        if '"Principal":"*"' in policy_text or '"Principal": "*"' in policy_text or '"Principal": {"AWS": "*"}' in policy_text:
            is_public = True
            reasons.append("Bucket policy allows public access")
    except s3_client.exceptions.from_code("NoSuchBucketPolicy") if hasattr(s3_client, "exceptions") else Exception:
        # No policy is fine
        pass
    except Exception as e:
        # ignore missing policy, surface other errors
        if "NoSuchBucketPolicy" not in str(e):
            reasons.append(f"Policy check failed: {e}")

    # Check public access block settings
    try:
        pab = s3_client.get_public_access_block(Bucket=bucket_name)
        config = pab.get("PublicAccessBlockConfiguration", {})
        # if all are False then public access blocks are not enabled
        if not any(config.values()):
            reasons.append("PublicAccessBlock is not restricting access")
    except Exception:
        # ignore missing config
        pass

    return is_public, reasons

def lambda_handler(event, context):
    # Destination bucket where the report will be stored. Prefer environment variable.
    report_bucket = os.environ.get("REPORT_BUCKET_NAME")
    if not report_bucket:
        raise ValueError("REPORT_BUCKET_NAME environment variable must be set")

    ec2 = boto3.client('ec2')
    s3_client = boto3.client('s3')
    apigw = boto3.client('apigateway')
    rds = boto3.client('rds')
    cloudfront = boto3.client('cloudfront')

    # Gather information, but be tolerant of permissions errors in whichever account it's run in.
    report = {"timestamp": datetime.datetime.utcnow().isoformat()}

    # S3 public buckets
    s3_public = []
    try:
        buckets = s3_client.list_buckets().get("Buckets", [])
        for b in buckets:
            name = b.get("Name")
            is_public, reasons = _is_bucket_public(s3_client, name)
            s3_public.append({
                "name": name,
                "is_public": is_public,
                "reasons": reasons
            })
    except Exception as e:
        report['s3_error'] = str(e)

    # EC2: public elastic IPs and instances with public IPs
    ec2_public = {"eips": [], "instances": []}
    try:
        addrs = ec2.describe_addresses().get("Addresses", [])
        for a in addrs:
            if a.get("PublicIp"):
                ec2_public["eips"].append({
                    "public_ip": a.get("PublicIp"),
                    "allocation_id": a.get("AllocationId"),
                    "domain": a.get("Domain")
                })
    except Exception as e:
        report['ec2_addresses_error'] = str(e)

    try:
        paginator = ec2.get_paginator('describe_instances')
        for page in paginator.paginate():
            for res in page.get("Reservations", []):
                for inst in res.get("Instances", []):
                    public_ip = inst.get("PublicIpAddress")
                    if public_ip:
                        ec2_public["instances"].append({
                            "instance_id": inst.get("InstanceId"),
                            "public_ip": public_ip,
                            "state": inst.get("State", {}).get("Name"),
                            "tags": inst.get("Tags", [])
                        })
    except Exception as e:
        report['ec2_instances_error'] = str(e)

    # CloudFront distributions
    cf_public = []
    try:
        paginator = cloudfront.get_paginator('list_distributions')
        # cloudfront paginator returns dict with DistributionList
        resp = cloudfront.list_distributions()
        dist_list = resp.get("DistributionList", {})
        for d in dist_list.get("Items", []):
            cf_public.append({
                "id": d.get("Id"),
                "domain": d.get("DomainName"),
                "enabled": d.get("Enabled"),
                "origins": [o.get("DomainName") for o in d.get("Origins", {}).get("Items", [])]
            })
    except Exception as e:
        report['cloudfront_error'] = str(e)

    # API Gateway REST APIs (public endpoints)
    apis = []
    try:
        rest = apigw.get_rest_apis().get("items", [])
        for api in rest:
            apis.append({
                "id": api.get("id"),
                "name": api.get("name"),
                "endpoint_configuration": api.get("endpointConfiguration")
            })
    except Exception as e:
        report['apigw_error'] = str(e)

    # RDS: public accessibility
    rds_public = []
    try:
        instances = rds.describe_db_instances().get("DBInstances", [])
        for db in instances:
            if db.get("PubliclyAccessible"):
                rds_public.append({
                    "db_instance_identifier": db.get("DBInstanceIdentifier"),
                    "endpoint": db.get("Endpoint", {}),
                    "engine": db.get("Engine")
                })
    except Exception as e:
        report['rds_error'] = str(e)

    report.update({
        "s3_public": s3_public,
        "ec2_public": ec2_public,
        "cloudfront": cf_public,
        "api_gateway": apis,
        "rds_public": rds_public
    })

    # Save JSON report to S3
    try:
        s3_client.put_object(
            Bucket=report_bucket,
            Key=f"report-{datetime.datetime.utcnow().date()}.json",
            Body=json.dumps(report, default=str).encode('utf-8'),
            ContentType='application/json'
        )
    except Exception as e:
        # if saving to S3 fails, return report in the Lambda response (caller should check)
        return {"status": "failed_to_save_report", "error": str(e), "report": report}

    return {"status": "ok", "report": report}
