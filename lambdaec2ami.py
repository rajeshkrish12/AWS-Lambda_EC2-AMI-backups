# Automated AMI Backups
# @author Rajesh krishnamoorthy - modified to tag name of ami and sns mail on execution
# This script will search for all instances having a tag with "Backup" or "backup"
# on it. As soon as we have the instances list, we loop through each instance
# and create an AMI of it. Also, it will look for a "Retention" tag key which
# will be used as a retention policy number in days. If there is no tag with
# that name, it will use a 7 days default value for each AMI.
#
# After creating the AMI it creates a "Name" of the instance tag and  "DeleteOn" tag on the AMI indicating when
# it will be deleted using the Retention value and another Lambda function 

import boto3
import collections
import datetime
import sys
import os
import pprint

ec = boto3.client('ec2')
aws_sns_arn = os.getenv('aws_sns_arn', None)

def send_to_sns(subject, message):
    if aws_sns_arn is None:
        return

    print "Sending notification to: %s" % aws_sns_arn

    client = boto3.client('sns')

    response = client.publish(
        TargetArn=aws_sns_arn,
        Message=message,
        Subject=subject)

    if 'MessageId' in response:
        print "Notification sent with message id: %s" % response['MessageId']
    else:
        print "Sending notification failed with response: %s" % str(response)



def lambda_handler(event, context):

    reservations = ec.describe_instances(
        Filters=[
            {'Name': 'tag-key', 'Values': ['backup', 'Backup']},
        ]
    ).get(
        'Reservations', []
    )

    instances = sum(
        [
            [i for i in r['Instances']]
            for r in reservations
        ], [])

    print "Found %d instances that need backing up" % len(instances)

    to_tag = collections.defaultdict(list)
    to_tag_name = collections.defaultdict(list)

    for instance in instances:
         try:
            ins_name = [
              str(t.get('Value')).split(',')for t in instance['Tags']
              if t['Key'] == 'Name'][0]
         except Exception:
                pass
         try:
            retention_days = [
                int(t.get('Value')) for t in instance['Tags']

                if t['Key'] == 'Retention'][0]
         except IndexError:
            retention_days = 7
            

            create_time = datetime.datetime.now()
            create_fmt = create_time.strftime('%Y-%m-%d-%M')
        
            AMIid = ec.create_image(InstanceId=instance['InstanceId'], Name="Lambda - " + instance['InstanceId'] + " from " + create_fmt, Description="Lambda created AMI of instance " + instance['InstanceId'] + " from " + create_fmt, NoReboot=True, DryRun=False)


            pprint.pprint(instance)
   
            ami_name = str(ins_name).strip('[]'"'")

            
            to_tag[retention_days].append(AMIid['ImageId'])
            to_tag_name[ami_name].append(AMIid['ImageId'])
            

            print "Retaining AMI %s of instance id %s and name %s for %d days" % (
                AMIid['ImageId'],
                instance['InstanceId'],
                ins_name,
                retention_days,
            )

    print to_tag.keys()
    print to_tag_name.keys()
    
    for ami_name in to_tag_name.keys():

        ec.create_tags(
            Resources=to_tag_name[ami_name],
            Tags=[
                {'Key': 'Name', 'Value': ami_name},
            ]
    )
    for retention_days in to_tag.keys():
        delete_date = datetime.date.today() + datetime.timedelta(days=retention_days)
        delete_fmt = delete_date.strftime('%m-%d-%Y')
        print "Will delete %d AMIs on %s" % (len(to_tag[retention_days]), delete_fmt)

    
        ec.create_tags(
            Resources=to_tag[retention_days],
            Tags=[
                {'Key': 'DeleteOn', 'Value': delete_fmt},


            ]
        )
    amis = to_tag_name.keys()
    message = "Hello,\n \nAmi creation has been initiated successfully for {} instances".format(amis)
    send_to_sns('EC2 AMI', message)
