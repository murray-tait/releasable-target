GIT_REF ?= refs/heads/$(shell git rev-parse --abbrev-ref HEAD)
GIT_SHA ?= $(shell git rev-parse HEAD)
SHA1_START := $(shell echo ${GIT_SHA} | cut -c -2)
SHA1_END := $(shell echo ${GIT_SHA} | cut -c 3-)
GIT_DIRTY ?= $(if $(shell git diff --stat),true,false)

CODEBUILD_UUID := $(shell cat /proc/sys/kernel/random/uuid)
CODEBUILD_BUILD_ID ?= uk-nhs-devspineservices-pdspoc:${CODEBUILD_UUID}

build_dir := target
S3_BUILD_BUCKET ?= org.murraytait.experiment.build.builds
ARTIFACT_NAME := releasable

src/main/cdk/.venv:
	cd src/main/cdk && \
	python3 -m venv .venv && \
	. .venv/bin/activate \
	python3 -m pip install --upgrade pip && \
	python3 -m pip install poetry && \
	poetry install\

${build_dir}/lambda.zip: src/main/bash/*
	mkdir -p ${build_dir}/lambda
	rm -rf target/lambda/*
	rm -f $@
	cp src/main/bash/* target/lambda
	cd target/lambda && zip -ur ../lambda.zip * && cd ../..

${build_dir}/terraform.zip: src/main/cdk/*
	mkdir -p ${build_dir}/terraform
	rm -rf target/terraform/*
	mkdir -p ${build_dir}/terraform/src/main/cdk
	rm -f $@
	rsync -a src/main/cdk/* target/terraform/src/main/cdk
	cd target/terraform && zip -ur ../terraform.zip * && cd ../..

${build_dir}/web.zip: src/main/web/*
	mkdir -p ${build_dir}/web
	rm -rf target/web/*
	rm -f $@
	src/main/bin/create_build_file
	rsync -a --exclude='config.js' src/main/web/* target/web
	cd target/web && zip -ur ../cloudfront.zip * && cd ../..

build: ${build_dir}/terraform.zip ${build_dir}/lambda.zip ${build_dir}/web.zip
 
clean:
	rm -rf target/*

install: build
	aws s3 cp --no-progress target/lambda.zip s3://${S3_BUILD_BUCKET}/builds/releasable/objects/${SHA1_START}/${SHA1_END}/lambda.zip
	aws s3 cp --no-progress target/lambda.zip s3://${S3_BUILD_BUCKET}/builds/releasable/${GIT_REF}/lambda.zip
	aws s3 cp --no-progress target/cloudfront.zip s3://${S3_BUILD_BUCKET}/builds/releasable/objects/${SHA1_START}/${SHA1_END}/cloudfront.zip
	aws s3 cp --no-progress target/cloudfront.zip s3://${S3_BUILD_BUCKET}/builds/releasable/${GIT_REF}/cloudfront.zip
	aws s3 cp --no-progress target/terraform.zip s3://${S3_BUILD_BUCKET}/builds/releasable/objects/${SHA1_START}/${SHA1_END}/terraform.zip
	aws s3 cp --no-progress target/terraform.zip s3://${S3_BUILD_BUCKET}/builds/releasable/${GIT_REF}/terraform.zip

default: build

all: clean install

tf-workspace-%:
	mkdir -p target/cdktf/stacks/release
	cd target/cdktf/stacks/release && terraform init
	. src/main/cdk/.venv/bin/activate
	cd src/main/cdk && cdktf synth 
	cd target/cdktf/stacks/release && terraform workspace select $*

tf-get:
	cd src/main/cdk && cdktf get

tf-synth:
	. src/main/cdk/.venv/bin/activate
	cd src/main/cdk && cdktf synth



tf-diff:
	. src/main/cdk/.venv/bin/activate
	cd src/main/cdk  && \
	cdktf diff

tf-deploy:
	. src/main/cdk/.venv/bin/activate
	cd src/main/cdk && cdktf deploy

tf-plan: tf-synth
	cd src/main/cdk && cdktf synth
	cd target/cdktf/stacks/release && terraform plan

tf-apply: tf-synth
	. src/main/cdk/.venv/bin/activate
	cd target/cdktf/stacks/release && terraform apply --auto-approve

