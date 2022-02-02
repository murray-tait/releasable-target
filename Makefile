build_dir := target
ARTIFACT_NAME := releasable
CDK_STACK=${build_dir}/cdktf/stacks/release
CDK_SRC=src/main/cdk
CDK_VENV_BASE=src/main/cdk
NODE_PATH=$(shell pwd)/node_modules/.bin

S3_BUILD_BUCKET ?= org.murraytait.experiment.build.builds
GIT_REF ?= refs/heads/$(shell git rev-parse --abbrev-ref HEAD)
GIT_SHA ?= $(shell git rev-parse HEAD)
SHA1_START := $(shell echo ${GIT_SHA} | cut -c -2)
SHA1_END := $(shell echo ${GIT_SHA} | cut -c 3-)
GIT_DIRTY ?= $(if $(shell git diff --stat),true,false)
GIT_REF_TYPE ?= branch

S3_OBJECT_LOCATION = s3://${S3_BUILD_BUCKET}/builds/${ARTIFACT_NAME}/objects/${SHA1_START}/${SHA1_END}
S3_REF_LOCATION = s3://${S3_BUILD_BUCKET}/builds/${ARTIFACT_NAME}/${GIT_REF}

CODEBUILD_UUID := $(shell cat /proc/sys/kernel/random/uuid)
CODEBUILD_BUILD_ID ?= uk-nhs-devspineservices-pdspoc:${CODEBUILD_UUID}

clean:
	rm -rf ${build_dir}

${CDK_VENV_BASE}.venv:
	cd ${CDK_VENV_BASE} && \
	python3 -m venv .venv && \
	. .venv/bin/activate \
	python3 -m pip install --upgrade pip && \
	python3 -m pip install poetry && \
	poetry install

${build_dir}/lambda.zip: src/main/bash/*
	mkdir -p ${build_dir}/lambda
	rm -rf target/lambda/*
	rm -f $@
	cp src/main/bash/* target/lambda
	cd target/lambda && zip -ur ../lambda.zip * && cd ../..

${build_dir}/terraform.zip: ${CDK_SRC}/*
	mkdir -p ${build_dir}/terraform
	rm -rf target/terraform/*
	mkdir -p ${build_dir}/terraform/${CDK_SRC}
	rm -f $@
	rsync -a ${CDK_SRC}/* ${build_dir}/terraform/${CDK_SRC}
	cd target/terraform && zip -ur ../terraform.zip * && cd ../..

${build_dir}/web.zip: src/main/web/*
	mkdir -p ${build_dir}/web
	rm -rf target/web/*
	rm -f $@
	src/main/bin/create_build_file
	rsync -a --exclude='config.js' src/main/web/* target/web
	cd target/web && zip -ur ../cloudfront.zip * && cd ../..

build: ${build_dir}/terraform.zip ${build_dir}/lambda.zip ${build_dir}/web.zip
 
install: build
	@if [ "${GIT_DIRTY}" = "false" ]; then \
		aws s3 cp --no-progress target/lambda.zip ${S3_OBJECT_LOCATION}/lambda.zip; \
		aws s3 cp --no-progress target/cloudfront.zip ${S3_OBJECT_LOCATION}/cloudfront.zip; \
		aws s3 cp --no-progress target/terraform.zip ${S3_OBJECT_LOCATION}/terraform.zip; \
	fi

	if [ "${GIT_REF_TYPE}" = "branch" ] || [ "${GIT_DIRTY}" = "false" ]; then \
		aws s3 cp --no-progress target/cloudfront.zip ${S3_REF_LOCATION}/cloudfront.zip; \
		aws s3 cp --no-progress target/lambda.zip ${S3_REF_LOCATION}/lambda.zip ; \
		aws s3 cp --no-progress target/terraform.zip ${S3_REF_LOCATION}/terraform.zip; \
	fi

${CDK_STACK}:
	mkdir -p ${CDK_STACK}
	echo Default > ${CDK_STACK}/.terraform/environment	

tf-workspace-%: ${CDK_STACK}
	echo $* > ${CDK_STACK}/environment
	cd ${CDK_STACK} && terraform init
	. ${CDK_VENV_BASE}/.venv/bin/activate
	cd ${CDK_SRC} && \
	${NODE_PATH}/cdktf synth 
	cd ${CDK_STACK} && terraform workspace select $*

tf-get:
	. ${CDK_VENV_BASE}/.venv/bin/activate && \
	cd ${CDK_SRC} && \
	${NODE_PATH}/cdktf get

tf-synth:
	. ${CDK_VENV_BASE}/.venv/bin/activate
	cd ${CDK_SRC} && \
	${NODE_PATH}/cdktf synth

tf-diff:
	. ${CDK_VENV_BASE}/.venv/bin/activate && \
	cd ${CDK_SRC} && \
	${NODE_PATH}/cdktf diff

tf-deploy:
	. ${CDK_VENV_BASE}/.venv/bin/activate
	cd ${CDK_SRC} && \
	${NODE_PATH}/cdktf deploy

tf-plan: tf-synth
	. ${CDK_VENV_BASE}/.venv/bin/activate && \
	cd ${CDK_STACK} && terraform plan

tf-apply: tf-synth
	. ${CDK_VENV_BASE}/.venv/bin/activate && \
	cd ${CDK_STACK} && terraform apply --auto-approve
