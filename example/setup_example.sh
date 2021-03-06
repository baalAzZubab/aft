#! /bin/bash

# initialize submodules
git submodule init
git submodule update

# apply patches
cd algorithms/cosmos
git am ../../patches/0001-Changes-to-make-introsort.cpp-usable-for-aft.patch
cd ../..

cd algorithms/sorting
git am ../../patches/0001-Changes-to-make-sorting-usable-as-gt-for-aft.patch
cd ../..

# thin out the code in cosmos, as its a big library
cd algorithms/cosmos/code
rm -rf $(ls | grep -v 'sorting')
cd sorting/src
rm -rf $(ls | grep -v 'intro_sort')
cd ../../../../..

# if something is broken in the submodules and they have to be downloaded new type
# git submodule deinit
# and then run this script again
