resource "aws_network_interface" "roombaht" {
  subnet_id = var.subnet_id
  security_groups = [
    var.security_group_id
  ]
  description = "${var.environment} roombaht"
  tags = {
    "Name" = "${var.environment} roombaht"
    "repo" = "Take3Presents/RoomBot"
  }
}

resource "aws_eip" "roombaht" {
  network_interface = aws_network_interface.roombaht.id
  domain = "vpc"
  tags = {
    "Name" = "${var.environment} roombaht"
    "repo" = "Take3Presents/RoomBot"
  }
}

resource "aws_instance" "roombaht" {
  ami = var.ami_id
  instance_type = "t2.medium"
  iam_instance_profile = var.iam_profile
  key_name = "roombaht"
  availability_zone = "${data.aws_region.roombaht.region}${var.availability_zone}"

  network_interface {
    network_interface_id = aws_network_interface.roombaht.id
    device_index = 0
  }

  root_block_device {
    encrypted = true
    kms_key_id = var.kms_key_id
    volume_size = var.root_size
    volume_type = "gp2"
    tags = {
      "Name" = "${var.environment} roombaht root"
      "repo" = "Take3Presents/RoomBot"
    }
  }
  tags = {
    "Name" = "${var.environment} roombaht"
    "repo" = "Take3Presents/RoomBot"
  }
}
