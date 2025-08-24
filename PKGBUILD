# Maintainer: Thorsten Foltz <thorsten.foltz@live.com>
pkgname=cai
pkgver=0.1.0
pkgrel=1
pkgdesc="Use LLM to create git commit messages."
arch=('any')
license=('MIT')
depends=('python' 'python-pip' 'python-yaml' 'python-openai')
source=()
sha256sums=()

build() {
    # Create a clean staging directory
    mkdir -p "$srcdir/$pkgname-$pkgver"

    # Copy only project files, skip makepkg internals
    for f in "$startdir"/*; do
        case "$(basename "$f")" in
            src|pkg) ;;  # skip makepkg working dirs
            *) cp -r "$f" "$srcdir/$pkgname-$pkgver"/ ;;
        esac
    done

    cd "$srcdir/$pkgname-$pkgver"

    # Optional: build a wheel (can skip, pip install . works too)
    python -m pip wheel . --wheel-dir "$srcdir/dist"
}

package() {
    cd "$srcdir/$pkgname-$pkgver"

    # Install the package system-wide in staged dir
    # This ensures console scripts go to /usr/bin
    python -m pip install --root="$pkgdir" --prefix=/usr .
}
