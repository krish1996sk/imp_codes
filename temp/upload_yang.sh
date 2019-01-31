
expect <(cat <<'EOD'
spawn bash -c "scp -oHostKeyAlgorithms=+ssh-dss svl-junos-d066.juniper.net:/volume/build/junos/18.3/release/18.3R1.1/ship/junos-yang-module-18.3R1.1.tar.gz ."
expect {
  -re ".*es.*o.*" {
    exp_send "yes\r"
    exp_continue
  }
  -re ".*sword.*" {
    exp_send "Omega_20\r"
  }
}
interact
EOD
)

mkdir -p ~/junos-yang-module-18.3R1.1
tar -xzvf junos-yang-module-18.3R1.1.tar.gz -C ~/junos-yang-module-18.3R1.1
cd ~/junos-yang-module-18.3R1.1

curl -u krish1996sk:74e10baf73888a2ba10c0d8ab3b5e40429a1da23 https://api.github.com/user/repos -d '{"name":"new_repo7"}'

git init
git add --all
git commit -m "First commit"
git remote add origin https://github.com/krish1996sk/imp_codes.git
git push -u -f origin master
cd ..
rm -rf ~/junos-yang-module-18.3R1.1
