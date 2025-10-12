module "staging" {
  source = "./host"
  environment = "staging"
  subnet_id = aws_subnet.public.id
  security_group_id = aws_security_group.roombaht.id
  ami_id = try(var.ami_id, data.aws_ami.jammy.id)
  iam_profile = aws_iam_instance_profile.roombaht.name
  kms_key_id = aws_kms_key.roombaht.arn
  availability_zone = var.availability_zone
  count = var.staging ? 1 : 0
}

module "production" {
  source = "./host"
  environment = "production"
  subnet_id = aws_subnet.public.id
  security_group_id = aws_security_group.roombaht.id
  ami_id = try(var.ami_id, data.aws_ami.jammy.id)
  iam_profile = aws_iam_instance_profile.roombaht.name
  kms_key_id = aws_kms_key.roombaht.arn
  availability_zone = var.availability_zone
  count = var.production ? 1 : 0
}
