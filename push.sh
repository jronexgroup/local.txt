#!/bin/bash

# Commit message input
read -p "Enter commit message: " COMMIT_MSG

# Check if message is empty
if [ -z "$COMMIT_MSG" ]; then
    echo "❌ Commit message cannot be empty."
    exit 1
fi

echo "📦 Adding files..."
git add .

echo "📝 Committing..."
git commit -m "$COMMIT_MSG"

if [ $? -ne 0 ]; then
    echo "❌ Commit failed."
    exit 1
fi

echo "🚀 Pushing..."
git push

echo "✅ Done!"
