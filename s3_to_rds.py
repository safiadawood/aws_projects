import pandas as pd
from sqlalchemy import create_engine
import boto3
import json
import os


def get_ssm_parameter(parameter_name, region_name):
    """
    Retrieve a parameter from AWS Systems Manager Parameter Store.

    Parameters:
    - parameter_name (str): The name of the parameter.
    - region_name (str): The AWS region where the parameter is stored.

    Returns:
    - str: The parameter value.
    """
    ssm_client = boto3.client('ssm', region_name=region_name)

    try:
        response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)
        return response['Parameter']['Value']
    except Exception as e:
        raise Exception(f"Error retrieving parameter from SSM Parameter Store: {e}")

def read_csv_from_s3(s3_path):
    """
    Read a CSV file from an S3 location into a pandas DataFrame.

    Parameters:
    - s3_path (str): S3 path to the CSV file (e.g., 's3://your-bucket/your-path/file.csv').

    Returns:
    - pd.DataFrame: A pandas DataFrame containing the CSV data.
    """
    s3_client = boto3.client('s3')
    bucket, key = s3_path.replace('s3://', '').split('/', 1)
    
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        df = pd.read_csv(response['Body'])
        return df
    except Exception as e:
        raise Exception(f"Error reading CSV from S3: {e}")


def get_rds_credentials(secret_name, region_name):
    """
    Retrieve RDS credentials from AWS Secrets Manager.

    Parameters:
    - secret_name (str): The name or ARN of the secret.
    - region_name (str): The AWS region where the secret is stored.

    Returns:
    - dict: A dictionary containing RDS credentials.
    """
    secrets_manager_client = boto3.client('secretsmanager', region_name=region_name)

    try:
        response = secrets_manager_client.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])
    except Exception as e:
        raise Exception(f"Error retrieving RDS credentials from Secrets Manager: {e}")


def connect_to_rds(credentials, database, hostname):
    """
    Create a connection to RDS using SQLAlchemy.

    Parameters:
    - credentials (dict): A dictionary containing RDS credentials.
    - database (str): The name of the database.

    Returns:
    - sqlalchemy.engine.base.Engine: A SQLAlchemy Engine object.
    """
    print(hostname)
    try:
        engine = create_engine(f"mysql+pymysql://{credentials['username']}:{credentials['password']}@{hostname}/{database}")
        #engine = create_engine(f"mysql+mysqlconnector://{credentials['username']}:{credentials['password']}@{credentials['host']}/{database}")
        return engine
    except Exception as e:
        raise Exception(f"Error connecting to RDS: {e}")


def load_table(engine, table_name, df):
    """
    Load a table in RDS using SQLAlchemy.

    Parameters:
    - engine (sqlalchemy.engine.base.Engine): A SQLAlchemy Engine object.
    - table_name (str): The name of the table.
    - df (pd.DataFrame): The DataFrame to be inserted into the table.
    """
    try:
        df.to_sql(table_name, con=engine, index=False, if_exists='replace')
        print("Table loaded successfully.")
    except Exception as e:
        raise Exception(f"Error loading table: {e}")


def get_aws_account_id():
    """
    Retrieve the AWS account ID associated with the credentials.

    Returns:
    - str: The AWS account ID.
    """
    sts_client = boto3.client('sts')
    try:
        response = sts_client.get_caller_identity()
        return response['Account']
    except Exception as e:
        raise Exception(f"Error retrieving AWS account ID: {e}")


def send_sns_notification(subject, message, sns_topic_arn, region_name):
    """
    Send an SNS notification.

    Parameters:
    - subject (str): The subject of the SNS message.
    - message (str): The content of the SNS message.
    - sns_topic_arn (str): The ARN of the SNS topic.
    - region_name (str): The AWS region where the SNS topic is located.
    """
    sns_client = boto3.client('sns', region_name=region_name)

    try:
        sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=subject,
            Message=message
        )
        print("Notification sent to SNS topic.")
    except Exception as e:
        raise Exception(f"Error sending SNS notification: {e}")


def lambda_handler(event, context):
    
    db_name = os.environ.get('dbname')
    print(db_name)
    # Extract information from the event
    
    file_name='sales_rds_excercise_full1.csv'

    # File path
    s3_csv_path = f's3://dehlive-sales-{get_aws_account_id()}-us-east-1/raw/maze/{file_name}'

    # AWS Secrets Manager details
    secret_name = 'dev/database-1/salesdb'
    region_name = 'us-east-1'

    # AWS SNS details
    sns_topic_arn = f'arn:aws:sns:us-east-1:{get_aws_account_id()}:dehtopic'
    sns_subject = 'Sales job failed to load RDS table'
    sns_message = 'Support Team, Please look into it.'
    
    rds_hostname_parameter_name = '/dev/rds/hostname'
    

    try:
        # Read CSV file
        df = read_csv_from_s3(s3_csv_path)

        # Get RDS credentials
        credentials = get_rds_credentials(secret_name, region_name)

        # Connect to RDS
        database = db_name
        rds_hostname = get_ssm_parameter(rds_hostname_parameter_name, region_name)
        engine = connect_to_rds(credentials, database,rds_hostname )

        # Assuming your MySQL table name is 'sales_data'
        table_name = 'sales'

        # Create table if not exists
        load_table(engine, table_name, df)

        print("Data successfully loaded into MySQL RDS.")

    except Exception as e:
        print(f"Error: {e}")

        # Send SNS notification on failure
        send_sns_notification(sns_subject, sns_message, sns_topic_arn, region_name)
        exit(1)