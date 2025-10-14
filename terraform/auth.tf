resource "aws_iam_policy" "roombaht" {
  name = "roombaht-host"
  description = "roombaht instance acccess controls"
  policy = templatefile("${path.module}/templates/roombaht.json",
    {
      key_id = aws_kms_key.roombaht.arn
      secret_id = aws_db_instance.roombaht[0].master_user_secret[0].secret_arn
    })
  tags = {
    "Name" = "roombaht host access"
    "repo" = "Take3Presents/RoomBot"
  }
  depends_on = [
    aws_db_instance.roombaht,
    aws_kms_key.roombaht
  ]
  count = (var.production || var.staging) ? 1 : 0
}

resource "aws_kms_key" "roombaht" {
  description = "The Roombaht Key"
}

resource "aws_iam_role" "roombaht" {
  name = "roombaht"
  path = "/"
  assume_role_policy = file("${path.module}/files/roombaht_role.json")
}

resource "aws_iam_role_policy_attachment" "roombaht" {
  role = aws_iam_role.roombaht.name
  policy_arn = aws_iam_policy.roombaht[0].arn
  count = (var.production || var.staging) ? 1 : 0
}

resource "aws_iam_instance_profile" "roombaht" {
  name = "roombaht"
  role = aws_iam_role.roombaht.name
}

resource "aws_security_group" "roombaht" {
  description = "roombaht rulez"
  vpc_id = aws_vpc.roombaht.id
}

resource "aws_security_group_rule" "ssh" {
  type = "ingress"
  from_port = 22
  to_port = 22
  protocol = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
  security_group_id = aws_security_group.roombaht.id
}

resource "aws_security_group_rule" "http" {
  type = "ingress"
  from_port = 80
  to_port = 80
  protocol = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
  security_group_id = aws_security_group.roombaht.id
}

resource "aws_security_group_rule" "https" {
  type = "ingress"
  from_port = 443
  to_port = 443
  protocol = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
  security_group_id = aws_security_group.roombaht.id
}

resource "aws_security_group_rule" "api" {
  type = "ingress"
  from_port = 8443
  to_port = 8443
  protocol = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
  security_group_id = aws_security_group.roombaht.id
}

resource "aws_security_group_rule" "outbound_all" {
  type = "egress"
  cidr_blocks = ["0.0.0.0/0"]
  to_port = 0
  from_port = 0
  protocol = "all"
  security_group_id = aws_security_group.roombaht.id
}

data "local_file" "roombaht_public_key" {
  filename = "${path.module}/files/roombaht.pub"
}

resource "aws_key_pair" "roombaht" {
  key_name = "roombaht"
  public_key = data.local_file.roombaht_public_key.content
}

resource "aws_security_group" "db" {
  description = "roombaht db"
  vpc_id = aws_vpc.roombaht.id
}

resource "aws_security_group_rule" "psql" {
  type = "ingress"
  from_port = 5432
  to_port = 5432
  protocol = "tcp"
  security_group_id = aws_security_group.db.id
  source_security_group_id = aws_security_group.roombaht.id
}
