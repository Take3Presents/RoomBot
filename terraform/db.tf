resource "aws_db_subnet_group" "roombaht" {
  name = "roombaht"
  subnet_ids = [
    aws_subnet.public.id,
    aws_subnet.alt_public.id
  ]
  tags = {
    "Name" = "roombaht"
    "repo" = "Take3Presents/RoomBot"
  }
}

resource "aws_db_instance" "roombaht" {
  engine = "postgres"
  engine_version = var.postgres_version
  identifier = "roombaht"
  allocated_storage = 20
  instance_class = "db.t3.small"
  username = "root"
  manage_master_user_password   = true
  master_user_secret_kms_key_id = aws_kms_key.roombaht.arn
  storage_encrypted = true
  kms_key_id = aws_kms_key.roombaht.arn
  multi_az = false
  allow_major_version_upgrade = false
  backup_retention_period = 14
  backup_target = "region"
  delete_automated_backups = true
  skip_final_snapshot = true
  availability_zone = "${data.aws_region.roombaht.region}${var.availability_zone}"
  db_subnet_group_name = aws_db_subnet_group.roombaht.name
  vpc_security_group_ids = [
    aws_security_group.db.id
  ]
  tags = {
    "Name" = "roombaht data tho"
    "repo" = "Take3Presents/RoomBot"
  }
  count = (var.production || var.staging) ? 1 : 0
}
