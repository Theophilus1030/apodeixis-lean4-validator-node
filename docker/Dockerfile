FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y curl git build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash lean
USER lean
WORKDIR /home/lean

RUN curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y --default-toolchain none

ENV PATH="/home/lean/.elan/bin:$PATH"

RUN mkdir validator_project
WORKDIR /home/lean/validator_project

RUN echo 'leanprover/lean4:v4.15.0' > lean-toolchain

RUN printf 'import Lake\n\
open Lake DSL\n\
\n\
package validator_project where\n\
\n\
lean_lib ValidatorProject where\n\
\n\
require mathlib from git\n\
  "https://github.com/leanprover-community/mathlib4" @ "v4.15.0"\n\
' > lakefile.lean

RUN echo 'def hello := "world"' > ValidatorProject.lean

RUN lake update && lake build ValidatorProject

WORKDIR /home/lean
COPY --chown=lean:lean entrypoint.sh /home/lean/entrypoint.sh
RUN chmod +x /home/lean/entrypoint.sh

ENTRYPOINT ["/home/lean/entrypoint.sh"]

WORKDIR /home/lean

COPY --chown=lean:lean CheckAxioms.lean /home/lean/CheckAxioms.lean

COPY --chown=lean:lean entrypoint.sh /home/lean/entrypoint.sh
RUN chmod +x /home/lean/entrypoint.sh

ENTRYPOINT ["/home/lean/entrypoint.sh"]