provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.tags
  }
}

resource "aws_ecr_repository" "application" {
  for_each             = toset(["backend", "worker", "frontend", "collab"])
  name                 = "${var.name_prefix}/${each.key}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = module.secrets.kms_key_arn
  }

  tags = var.tags
}

# 1. Secrets Management & KMS Encryption
module "secrets" {
  source      = "./modules/secrets"
  name_prefix = var.name_prefix
  tags        = var.tags
}

# 2. Networking (VPC, Subnets, NAT Gateways)
module "vpc" {
  source             = "./modules/vpc"
  name_prefix        = var.name_prefix
  cidr_block         = var.vpc_cidr
  availability_zones = var.availability_zones
  enable_nat_gateway = true
  single_nat_gateway = false
  tags               = var.tags
}

# 3. Managed EKS Cluster
module "eks" {
  source              = "./modules/eks"
  cluster_name        = "${var.name_prefix}-eks"
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnet_ids
  kms_key_arn         = module.secrets.kms_key_arn
  kubernetes_version  = "1.35"
  node_instance_types = ["m6i.xlarge"]
  desired_nodes       = 3
  min_nodes           = 2
  max_nodes           = 10
  tags                = var.tags
}

# 4. PostgreSQL RDS Multi-AZ Database
module "postgresql" {
  source              = "./modules/postgresql"
  name_prefix         = var.name_prefix
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.database_subnet_ids
  allowed_cidr_blocks = [module.vpc.vpc_cidr]
  kms_key_arn         = module.secrets.kms_key_arn
  instance_class      = "db.r6g.xlarge"
  database_name       = "agentspace"
  admin_username      = "agentspace_admin"
  admin_password      = module.secrets.db_password
  multi_az            = true
  tags                = var.tags
}

# 5. Object Storage (S3 CAS Artifacts)
module "storage" {
  source      = "./modules/storage"
  name_prefix = var.name_prefix
  kms_key_arn = module.secrets.kms_key_arn
  tags        = var.tags
}

# 6. ElastiCache Redis Cluster
module "cache" {
  source              = "./modules/cache"
  name_prefix         = var.name_prefix
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.database_subnet_ids
  allowed_cidr_blocks = [module.vpc.vpc_cidr]
  kms_key_arn         = module.secrets.kms_key_arn
  node_type           = "cache.r6g.large"
  num_cache_clusters  = 2
  auth_token          = module.secrets.redis_auth_token
  tags                = var.tags
}

# 7. Shared project workspaces (ReadWriteMany for API, workers and editor)
module "workspace" {
  source      = "./modules/workspace"
  name_prefix = var.name_prefix
  vpc_id      = module.vpc.vpc_id
  vpc_cidr    = module.vpc.vpc_cidr
  subnet_ids  = module.vpc.private_subnet_ids
  kms_key_arn = module.secrets.kms_key_arn
  tags        = var.tags
}

# 8. Messaging (SQS, DLQ, SNS)
module "messaging" {
  source      = "./modules/messaging"
  name_prefix = var.name_prefix
  kms_key_arn = module.secrets.kms_key_arn
  tags        = var.tags
}

# 9. GPU Worker Node Group (Inference & Vision)
module "gpu" {
  source         = "./modules/gpu"
  cluster_name   = module.eks.cluster_name
  subnet_ids     = module.vpc.private_subnet_ids
  node_role_arn  = module.eks.node_role_arn
  instance_types = ["g5.xlarge"]
  min_nodes      = 0
  max_nodes      = 4
  desired_nodes  = 0
  tags           = var.tags
}

# 10. Monitoring & Production Alarms
module "monitoring" {
  source                     = "./modules/monitoring"
  name_prefix                = var.name_prefix
  kms_key_arn                = module.secrets.kms_key_arn
  db_instance_id             = module.postgresql.db_instance_id
  redis_replication_group_id = "${var.name_prefix}-redis"
  retention_in_days          = 90
  tags                       = var.tags
}
