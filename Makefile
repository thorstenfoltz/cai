#!/usr/bin/make -f

UV := uv
SHELL := /bin/bash
MEGALINTER_VERSION := $(shell sed -n 's/^MEGALINTER_VERSION: *//p' .mega-linter.yml)
MEGALINTER_IMAGE := ghcr.io/oxsecurity/megalinter:$(MEGALINTER_VERSION)
# --platform: the image is amd64 only. z: relabels the mount on SELinux hosts, ignored elsewhere.
MEGALINTER_RUN := docker run --rm --platform linux/amd64 -v "$(CURDIR):/tmp/lint:rw,z"

.PHONY: help lint check-docker lint-fix add-lint-hook clean test

help: ## Shows this help message
	@echo "Available commands:"
	@awk '/^[a-zA-Z_-]+:.*## / { printf "  %-20s %s\n", $$1, substr($$0, index($$0, "##") + 3) }' $(MAKEFILE_LIST)

add-lint-hook: ## Adds a git pre-push hook to automatically run 'lint' before pushing
	@echo "#!/bin/bash" > .git/hooks/pre-push
	@echo "make lint" >> .git/hooks/pre-push
	@chmod +x .git/hooks/pre-push
	@echo "make test" >> .git/hooks/pre-push
	@echo "Pre-push hook added. The 'lint' command will now run before each push."
	@echo "Pre-push hook added. The 'test' command will now run before each push."	

check-docker: ## Checks if docker is installed
	@if ! command -v docker &> /dev/null; then \
		echo "Docker is not installed. Please install it."; \
		exit 1; \
	else \
		echo "Docker version:"; \
		docker --version; \
	fi

clean: ## Clean cache of uv and delete virtual environment
	@$(UV) cache clean
	@rm -rf .venv

lint: ## Checks the branch name and runs MegaLinter
	@sh ./.linters/check_git_branch_name.sh
	@$(MEGALINTER_RUN) $(MEGALINTER_IMAGE)

lint-fix: ## Runs MegaLinter and applies its fixes
	@$(MEGALINTER_RUN) -e APPLY_FIXES=all $(MEGALINTER_IMAGE)

test: ## Runs tests
	@$(UV) run pytest