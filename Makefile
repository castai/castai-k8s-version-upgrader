default: release

PLATFORMS = linux/amd64,linux/arm64
APP= "ronakpatildocker/castai-node-replicate"
TAG_LATEST=$(APP):latest
TAG_VERSION=$(APP):v0.1


pull:
	docker pull $(TAG_LATEST)

build:
	@echo "==> Building node-roate-image"
	docker build --cache-from $(TAG_LATEST) --platform linux/amd64 -t $(TAG_LATEST) -t $(TAG_VERSION) .

multiarch_build_push:
	@echo "==> Building node-roate-image multiarch"
	docker buildx create --use
	docker buildx build  --platform $(PLATFORMS)  -t $(TAG_VERSION)  -t $(TAG_LATEST) --push .

