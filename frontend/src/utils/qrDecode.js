import jsQR from 'jsqr'

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('无法读取图片'))
    img.src = src
  })
}

/**
 * 从二维码图片中解析文本（通常为 socks5 / vmess / vless 链接）。
 */
export async function decodeQrFromFile(file) {
  if (!file) {
    throw new Error('请选择图片')
  }
  const url = URL.createObjectURL(file)
  try {
    const img = await loadImage(url)
    const canvas = document.createElement('canvas')
    canvas.width = img.naturalWidth || img.width
    canvas.height = img.naturalHeight || img.height
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      throw new Error('浏览器不支持图片解析')
    }
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
    const result = jsQR(imageData.data, imageData.width, imageData.height)
    if (!result?.data?.trim()) {
      throw new Error('未识别到二维码，请换一张更清晰的图片')
    }
    return result.data.trim()
  } finally {
    URL.revokeObjectURL(url)
  }
}
