#!/usr/bin/make -f

PIP := pipx
UV := uv
SHELL := /bin/bash

.PHONY: check-python check-pipx install-uv virt sync create-alias help setup create-linter lint check-docker check-npx lint-fix add-lint-hook clean

help: ## Shows this help message
	@echo "Available commands:"
	@awk '/^[a-zA-Z_-]+:.*## / { printf "  %-20s %s\n", $$1, substr($$0, index($$0, "##") + 3) }' $(MAKEFILE_LIST)

add-lint-hook: ## Adds a git pre-push hook to automatically run 'lint' before pushing
	@echo "#!/bin/bash" > .git/hooks/pre-push
	@echo "make lint" >> .git/hooks/pre-push
	@chmod +x .git/hooks/pre-push
	@echo "Pre-push hook added. The 'lint' command will now run before each push."

check-docker: ## Checks if docker is installed
	@if ! command -v docker &> /dev/null; then \
		echo "Docker is not installed. Please install it."; \
		exit 1; \
	else \
		echo "Docker version:"; \
		docker --version; \
	fi

check-npx: ## Checks if npx is installed
	@if ! command -v npx &> /dev/null; then \
		echo "npx is not installed. Please install it."; \
		exit 1; \
	else \
		echo "npx version:"; \
		npx --version; \
	fi

check-pipx: ## Checks if pip is installed
	@if ! command -v $(PIP) &> /dev/null; then \
		echo "Pip is not installed. Please install it."; \
		exit 1; \
	else \
		echo "Pip version:"; \
		$(PIP) --version; \
	fi

check-python: ## Checks if python is installed and shows the version
	@if ! command -v python3$ &> /dev/null; then \
		echo "Python is not installed. Please install it."; \
		exit 1; \
	else \
		echo "Python version:"; \
		python3 --version; \
	fi

clean: ## Clean cache of uv and delete virtual environment
	@$(UV) cache clean
	@rm -rf .venv

create-alias: ## Creates an alias to start the virtual environment with the simple command 'virt'
	@read -p "Do you want to create an alias for the virtual environment? (y/n): " choice; \
	if [ "$$choice" = "y" ]; then \
		shell=$$SHELL; \
		if echo "$$shell" | grep -q "bash"; then \
			echo "alias virt='source .venv/bin/activate'" >> ~/.bashrc; \
			echo "Alias added to ~/.bashrc. Please restart your shell to use it. Start it with by executing virt."; \
		elif echo "$$shell" | grep -q "zsh"; then \
			echo "alias virt='source .venv/bin/activate'" >> ~/.zshrc; \
			echo "Alias added to ~/.zshrc. Please restart your shell to use it. Start it with by executing virt."; \
		elif echo "$$shell" | grep -q "fish"; then \
			echo "alias virt='source .venv/bin/activate'" >> ~/.config/fish/config.fish; \
			echo "Alias added to ~/.config/fish/config.fish. Please restart your shell to use it. Start it with by executing virt."; \
		else \
			echo "Shell not recognized. Please add the alias manually."; \
		fi; \
	else \
		echo "Alias creation skipped."; \
	fi;

create-linter: ## Creates a dbt linter (sqlfluff) docker container
	@docker buildx build -t sqlfluff-dbt-linter -f ./docker/sqlfluff-dbt-linter . --no-cache
	
install-uv: ## Installs package uv by using pip
	@$(PIP) install $(UV)

lint:
	@sh ./.linters/check_git_branch_name.sh
	@npx mega-linter-runner	--flavor python

lint-fix: ## Lints the code using sqlfluff and fixes the issues
	@npx mega-linter-runner --fix

setup: ## Executes check-python, check-pipx, check-docker, check-npx, install-uv, virt, create-alias, create-linter and add-lint-hook
	@$(MAKE) check-python
	@$(MAKE) check-pipx
	@$(MAKE) check-docker
	@$(MAKE) check-npx
	@$(MAKE) install-uv
	@$(MAKE) virt
	@$(MAKE) create-alias
	@$(MAKE) create-linter
	@$(MAKE) add-lint-hook

sync: ## Installs or updates the current packages defined in pyproject.toml
	@$(UV) sync

virt: ## Creates a virtual environment called .venv
	@$(UV) venv
	@echo "execute 'source .venv/bin/activate' to activate virtual environment"
