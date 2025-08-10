import boto3
import json
import os
from datetime import datetime

def lambda_handler(event, context):
    s3_client = boto3.client('s3')
    ec2_client = boto3.client('ec2')
    cloudfront_client = boto3.client('cloudfront')
    apigw_client = boto3.client('apigateway')
    rds_client = boto3.client('rds')

    report_bucket = os.environ.get('REPORT_BUCKET_NAME')
    if not report_bucket:
        return {
            'statusCode': 500,
            'body': 'Environment variable REPORT_BUCKET_NAME is not set'
        }

    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    report = {
        "S3": [],
        "EC2": [],
        "CloudFront": [],
        "APIGateway": [],
        "RDS": []
    }

    # S3 Buckets
    try:
        s3_buckets = s3_client.list_buckets()
        for bucket in s3_buckets.get('Buckets', []):
            bucket_name = bucket['Name']
            try:
                acl = s3_client.get_bucket_acl(Bucket=bucket_name)
                for grant in acl.get('Grants', []):
                    grantee = grant.get('Grantee', {})
                    if grantee.get('URI') in [
                        'http://acs.amazonaws.com/groups/global/AllUsers',
                        'http://acs.amazonaws.com/groups/global/AuthenticatedUsers'
                    ]:
                        report["S3"].append({
                            "Bucket": bucket_name,
                            "Access": grantee.get('URI')
                        })
            except Exception as e:
                pass
    except Exception as e:
        pass

    # EC2 Public IPs
    try:
        reservations = ec2_client.describe_instances()
        for res in reservations['Reservations']:
            for inst in res['Instances']:
                if 'PublicIpAddress' in inst:
                    report["EC2"].append({
                        "InstanceId": inst['InstanceId'],
                        "PublicIp": inst['PublicIpAddress']
                    })
    except Exception:
        pass

    # CloudFront
    try:
        distributions = cloudfront_client.list_distributions()
        for dist in distributions.get('DistributionList', {}).get('Items', []):
            report["CloudFront"].append({
                "Id": dist['Id'],
                "DomainName": dist['DomainName']
            })
    except Exception:
        pass

    # API Gateway
    try:
        apis = apigw_client.get_rest_apis()
        for api in apis.get('items', []):
            endpoint = f"https://{api['id']}.execute-api.{apigw_client.meta.region_name}.amazonaws.com"
            report["APIGateway"].append({
                "Id": api['id'],
                "Name": api['name'],
                "Endpoint": endpoint
            })
    except Exception:
        pass

    # RDS
    try:
        dbs = rds_client.describe_db_instances()
        for db in dbs['DBInstances']:
            if db.get('PubliclyAccessible'):
                report["RDS"].append({
                    "DBInstanceIdentifier": db['DBInstanceIdentifier'],
                    "Endpoint": db['Endpoint']['Address']
                })
    except Exception:
        pass

    # Save JSON
    json_key = f"report-{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    s3_client.put_object(
        Bucket=report_bucket,
        Key=json_key,
        Body=json.dumps(report, indent=2),
        ContentType='application/json'
    )

    # Save HTML
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AWS Public Asset Exposure Map</title>
<style>
    body {{
        font-family: Arial, sans-serif;
        margin: 20px;
    }}
    table {{
        border-collapse: collapse;
        width: 100%;
    }}
    th, td {{
        border: 1px solid #ddd;
        padding: 8px;
    }}
    th {{
        background-color: #f2f2f2;
    }}
</style>
</head>
<body>
<h1>AWS Public Asset Exposure Map</h1>
<p>Generated on {timestamp}</p>
<div id="report"></div>
<script type="application/json" id="report-data">
{json.dumps(report, indent=2)}
</script>
<script>
    const data = JSON.parse(document.getElementById('report-data').textContent);
    const container = document.getElementById('report');
    for (const [service, assets] of Object.entries(data)) {{
        const h2 = document.createElement('h2');
        h2.textContent = service;
        container.appendChild(h2);
        if (!assets.length) {{
            const p = document.createElement('p');
            p.textContent = 'No public assets found';
            container.appendChild(p);
            continue;
        }}
        const table = document.createElement('table');
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        Object.keys(assets[0]).forEach(key => {{
            const th = document.createElement('th');
            th.textContent = key;
            headerRow.appendChild(th);
        }});
        thead.appendChild(headerRow);
        table.appendChild(thead);
        const tbody = document.createElement('tbody');
        assets.forEach(item => {{
            const row = document.createElement('tr');
            Object.values(item).forEach(val => {{
                const td = document.createElement('td');
                td.textContent = val;
                row.appendChild(td);
            }});
            tbody.appendChild(row);
        }});
        table.appendChild(tbody);
        container.appendChild(table);
    }}
</script>
</body>
</html>"""

    html_key = f"report-{datetime.utcnow().strftime('%Y-%m-%d')}.html"
    s3_client.put_object(
        Bucket=report_bucket,
        Key=html_key,
        Body=html_content.encode('utf-8'),
        ContentType='text/html'
    )

    return {
        'statusCode': 200,
        'body': json.dumps({
            'json_report_key': json_key,
            'html_report_key': html_key
        })
    }