build_dir := ${CURDIR}/target
default:

${build_dir}/terraform.zip: src/main/terraform/*
	mkdir -p ${build_dir}/terraform
	rm -rf ${build_dir}/terraform/*
	rm -f $@
	rsync -a --exclude='.*' --exclude='.*' --exclude='graph.*' src/main/terraform/ ${build_dir}/terraform
	cd target/terraform && zip -ur ../terraform.zip * && cd ../..

${build_dir}/lambda.zip: src/main/bash/*
	mkdir -p ${build_dir}/lambda
	rm -rf target/lambda/*
	rm -f $@
	cp src/main/bash/* target/lambda
	cd target/terraform && zip -ur ../lambda.zip * && cd ../..

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
	aws s3 cp --no-progress target/lambda.zip s3://${S3_BUILD_BUCKET}/builds/releasable-target/objects/${SHA1_START}/${SHA1_END}/lambda.zip
	aws s3 cp --no-progress target/lambda.zip s3://${S3_BUILD_BUCKET}/builds/releasable-target/refs/${CODEBUILD_WEBHOOK_TRIGGER}/lambda.zip
	aws s3 cp --no-progress target/cloudfront.zip s3://${S3_BUILD_BUCKET}/builds/releasable-target/objects/${SHA1_START}/${SHA1_END}/cloudfront.zip
	aws s3 cp --no-progress target/cloudfront.zip s3://${S3_BUILD_BUCKET}/builds/releasable-target/refs/${CODEBUILD_WEBHOOK_TRIGGER}/cloudfront.zip
	aws s3 cp --no-progress target/terraform.zip s3://${S3_BUILD_BUCKET}/builds/releasable-target/objects/${SHA1_START}/${SHA1_END}/terraform.zip
	aws s3 cp --no-progress target/terraform.zip s3://${S3_BUILD_BUCKET}/builds/releasable-target/refs/${CODEBUILD_WEBHOOK_TRIGGER}/terraform.zip

default: build

all: clean install