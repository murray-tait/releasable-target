
module "main" {
  source = "git@github.com:deathtumble/terraform_modules.git//modules/api_gateway?ref=v0.4.0"
  # source            = "../../../../terraform/modules/api_gateway"
  aws_region        = module.common.aws_region
  fqdn              = module.common.fqdn
  zone_id           = data.aws_route53_zone.environment.zone_id
  certificate_arn   = data.aws_acm_certificate.main.arn
  web_acl_id        = data.aws_wafregional_web_acl.main.id
  lambda_invoke_arn = aws_lambda_function.main.invoke_arn
}
