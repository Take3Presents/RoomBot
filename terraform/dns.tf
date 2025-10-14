resource "aws_route53_zone" "roombaht" {
  name = var.domain
  tags = {
    "Name" = "roombaht lives here"
    "repo" = "Take3Presents/RoomBot"
  }
}

 resource "aws_route53_record" "staging" {
   zone_id = aws_route53_zone.roombaht.id
   name = "staging.${var.domain}"
   type = "A"
   ttl = "300"
   records = [module.staging[0].public_ip]
   count = var.staging ? 1 : 0
}

resource "aws_route53_record" "prod" {
  zone_id = aws_route53_zone.roombaht.id
  name = "${var.domain}"
  type = "A"
  ttl = "300"
  records = [module.production[0].public_ip]
  count = var.production ? 1 : 0
}
