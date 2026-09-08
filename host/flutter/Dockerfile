FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

ARG FLUTTER_VERSION=3.47.0
ARG ANDROID_CMDLINE_TOOLS_VERSION=15859902

ENV FLUTTER_HOME=/opt/flutter
ENV ANDROID_HOME=/opt/android-sdk
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV PUB_CACHE=/root/.pub-cache

ENV PATH="${FLUTTER_HOME}/bin:${FLUTTER_HOME}/bin/cache/dart-sdk/bin:${ANDROID_HOME}/platform-tools:${ANDROID_HOME}/cmdline-tools/latest/bin:${PUB_CACHE}/bin:${PATH}"

RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    unzip \
    zip \
    xz-utils \
    ca-certificates \
    gnupg \
    build-essential \
    libglu1-mesa \
    openjdk-17-jdk \
    ruby-full \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Flutter
RUN git clone \
    https://github.com/flutter/flutter.git \
    ${FLUTTER_HOME} \
    && cd ${FLUTTER_HOME} \
    && git checkout ${FLUTTER_VERSION}

RUN git config --global --add safe.directory ${FLUTTER_HOME}

RUN flutter config --no-analytics \
    && flutter config --enable-web \
    && flutter precache --android --web

# Android SDK
RUN mkdir -p ${ANDROID_HOME}/cmdline-tools

RUN wget -q \
    https://dl.google.com/android/repository/commandlinetools-linux-${ANDROID_CMDLINE_TOOLS_VERSION}_latest.zip \
    -O /tmp/android-tools.zip \
    && unzip -q /tmp/android-tools.zip -d /tmp/android-tools \
    && mkdir -p ${ANDROID_HOME}/cmdline-tools/latest \
    && mv /tmp/android-tools/cmdline-tools/* \
       ${ANDROID_HOME}/cmdline-tools/latest/ \
    && rm -rf /tmp/android-tools \
    && rm /tmp/android-tools.zip

RUN yes | sdkmanager --licenses >/dev/null

RUN sdkmanager \
    "platform-tools" \
    "platforms;android-36" \
    "build-tools;36.0.0" \
    "build-tools;28.0.3"

# Bundler
RUN gem install bundler --version 4.0.20 --no-document

# Firebase CLI
RUN npm install -g firebase-tools@15.29.0

WORKDIR /workspace

CMD ["bash"]
