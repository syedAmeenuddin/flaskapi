from flask import Flask, request, jsonify
import boto3
import os
import uuid
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

app = Flask(__name__)

# AWS Configurations
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
SQS_QUEUE_NAME = os.getenv("SQS_QUEUE_NAME")
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# AWS Clients
s3_client = boto3.client("s3", region_name=AWS_REGION)
sqs_client = boto3.resource("sqs", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)

table = dynamodb.Table(DYNAMODB_TABLE_NAME)
queue = sqs_client.get_queue_by_name(QueueName=SQS_QUEUE_NAME)
print(f"Using SQS Queue: {SQS_QUEUE_NAME, queue}")

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Welcome to the Flask API!"})

@app.route("/upload/", methods=["POST"])
def upload_image():
    try:
        # Get the uploaded file
        file = request.files["file"]
        file_extension = file.filename.split(".")[-1]
        unique_id = str(uuid.uuid4())
        s3_key = f"uploads/{unique_id}.{file_extension}"

        # Upload to S3
        s3_client.upload_fileobj(file, S3_BUCKET_NAME, s3_key, ExtraArgs={"ContentType": file.content_type})
        image_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"

        # Create job record in DynamoDB
        enhancement_id = unique_id
        created_at = round(time.time())

        table.put_item(
            Item={
                "enhancementId": enhancement_id,
                "imageUrl": image_url,
                "createdAt": created_at,
                "status": "pending"
            }
        )

        message_deduplication_id = str(uuid.uuid4())
        queue.send_message(
            MessageBody=str({"enhancementId": enhancement_id, "imageUrl": image_url}),
            MessageGroupId="default-group",  # FIFO queues require a MessageGroupId
            MessageDeduplicationId=message_deduplication_id  # Ensuring uniqueness
        )

        return jsonify({"message": "File uploaded and job created", "enhancementId": enhancement_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/status/<enhancement_id>", methods=["GET"])
def check_status(enhancement_id):
    try:
        response = table.get_item(Key={"enhancementId": enhancement_id})
        if "Item" not in response:
            return jsonify({"error": "Job not found"}), 404

        return jsonify(response["Item"])

    except Exception as e:
        return jsonify({"error": f"Error retrieving status: {str(e)}"}), 500

@app.route("/result/<enhancement_id>", methods=["GET"])
def get_result(enhancement_id):
    try:
        response = table.get_item(Key={"enhancementId": enhancement_id})
        if "Item" not in response:
            return jsonify({"error": "Job not found"}), 404

        job = response["Item"]
        if job.get("status") != "completed":
            return jsonify({"message": "Job is still in progress", "status": job.get("status")})

        enhanced_image_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{job['enhancedImageS3Key']}"
        return jsonify({"message": "Enhancement completed", "image_url": enhanced_image_url})

    except Exception as e:
        return jsonify({"error": f"Error retrieving result: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)