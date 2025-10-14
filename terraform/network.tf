resource "aws_vpc" "roombaht" {
  cidr_block = "10.0.69.0/24"
  tags = {
    "Name" = "roombaht"
    "repo" = "Take3Presents/RoomBot"
  }
}

resource "aws_internet_gateway" "router" {
  vpc_id = aws_vpc.roombaht.id
  tags = {
    "Name" = "roombaht interwebs"
    "repo" = "Take3Presents/RoomBot"
  }
}

resource "aws_subnet" "public" {
  vpc_id = aws_vpc.roombaht.id
  cidr_block = "10.0.69.0/28"
  availability_zone = "${data.aws_region.roombaht.region}${var.availability_zone}"
  tags = {
    "Name" = "roombaht net"
    "repo" = "Take3Presents/RoomBot"
  }
}

resource "aws_subnet" "alt_public" {
  vpc_id = aws_vpc.roombaht.id
  cidr_block = "10.0.69.16/28"
  availability_zone = "${data.aws_region.roombaht.region}${var.alt_availability_zone}"
  tags = {
    "Name" = "roombaht net alternate"
    "repo" = "Take3Presents/RoomBot"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.roombaht.id
  tags = {
    "Name" = "roombaht"
    "repo" = "Take3Presents/RoomBot"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "alt_public" {
  subnet_id = aws_subnet.alt_public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route" "public_default" {
  route_table_id = aws_route_table.public.id
  gateway_id = aws_internet_gateway.router.id
  destination_cidr_block = "0.0.0.0/0"
}
