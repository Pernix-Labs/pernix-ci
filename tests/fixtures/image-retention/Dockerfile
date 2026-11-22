# scratch + ARG SEED label: each SEED gives a distinct config, so a distinct manifest digest.
# COPY gives the image one layer (no RUN, no base pull).
FROM scratch
ARG SEED=0
LABEL selftest.seed=${SEED}
COPY Dockerfile /seed
