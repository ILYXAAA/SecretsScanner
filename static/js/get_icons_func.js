function getIcon(name, size = 24, marginTop = 0, marginRight = 0, marginBottom = 0, marginLeft = 0) {
    return `<img src="/secret_scanner/static/icons/${name}.svg"
                 alt="${name}"
                 width="${size}"
                 height="${size}"
                 style="
                    vertical-align: middle;
                    margin-top: ${marginTop}px;
                    margin-right: ${marginRight}px;
                    margin-bottom: ${marginBottom}px;
                    margin-left: ${marginLeft}px;
                 ">`;
}
