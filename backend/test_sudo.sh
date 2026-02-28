sudo -n true
if [ $? -eq 0 ]; then
    echo "passwordless"
else
    echo "needs password"
fi
