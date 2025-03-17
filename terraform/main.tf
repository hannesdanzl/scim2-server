provider "aws" {
  region = "us-east-1" # Change as needed
}

resource "aws_api_gateway_rest_api" "scim2" {
  name        = "Scim2ApiGateway"
  description = "A SCIM2 service accessible through a public gateway"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.scim2.id
  parent_id   = aws_api_gateway_rest_api.scim2.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "proxy" {
  rest_api_id   = aws_api_gateway_rest_api.scim2.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "lambda" {
  rest_api_id = aws_api_gateway_rest_api.scim2.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.scim2.invoke_arn
}

resource "aws_api_gateway_deployment" "scim2" {
  depends_on = [aws_api_gateway_integration.lambda]
  rest_api_id = aws_api_gateway_rest_api.scim2.id
  stage_name  = "Prod"
}

resource "aws_lambda_function" "scim2" {
  function_name = "Scim2ServiceHandler"
  description   = "ScimService"
  filename      = "./src/lambda.zip" # Package your Python function as a zip
  handler       = "lambda.lambda_handler"
  runtime       = "python3.10"
  memory_size   = 256
  timeout       = 600
  role          = aws_iam_role.lambda_exec.arn

  environment {
    variables = {
      Log_Level = "INFO"
    }
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scim2.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.scim2.execution_arn}/*/*"
}

resource "aws_iam_role" "lambda_exec" {
  name = "lambda_exec_role"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow"
    }
  ]
}
EOF
}

resource "aws_iam_policy_attachment" "lambda_logs" {
  name       = "lambda_logs"
  roles      = [aws_iam_role.lambda_exec.name]
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
