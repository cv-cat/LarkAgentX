演示用头像。首页(`src/home/Home.tsx`)和 `dev/seed_demo.py` 共用这些文件。人名、公司和聊天内容都是虚构的,与照片中的人无关。

## 照片

来自 [Unsplash](https://unsplash.com),按 [Unsplash License](https://unsplash.com/license) 使用(可免费用于商业和非商业用途,无需署名;这里仍列出作者)。下载时用 Unsplash 的图片参数裁成 256×256,人像按人脸裁(`crop=faces`),猫狗、花和风景按画面主体裁(`crop=entropy`):
`https://images.unsplash.com/<图片 id>?w=256&h=256&fit=crop&crop=faces&q=82&fm=jpg`

和真实通讯录一样,有人用自拍,也有人用宠物、花或风景:周雨桐是猫,许嘉禾是柯基,顾言是山景,妈妈是牡丹。

| 文件 | 图片 id | 作者 | 原图 |
|---|---|---|---|
| lin-zhixia.jpg | photo-1758691737605-69a0e78bd193 | Vitaly Gariev | https://unsplash.com/photos/APjRQ59peUg |
| chen-siyuan.jpg | photo-1544168190-79c17527004f | Juan Encalada | https://unsplash.com/photos/WC7KIHo13Fc |
| zhou-yutong.jpg | photo-1768220794289-37de4bb51eeb | Andrea Caramello | https://unsplash.com/photos/69Vyq6-w49c |
| song-yining.jpg | photo-1761933808230-9a2e78956daa | Conikal | https://unsplash.com/photos/_DlHQIvieJA |
| xu-jiahe.jpg | photo-1713575314497-2795fab05bb2 | Joycelyn Hung | https://unsplash.com/photos/50birCocEv0 |
| gu-yan.jpg | photo-1506905925346-21bda4d32df4 | Sam Ferrara | https://unsplash.com/photos/1527pjeb6jg |
| he-jiayi.jpg | photo-1758600587839-56ba05596c69 | Vitaly Gariev | https://unsplash.com/photos/s3aDHKxHZSc |
| mom.jpg | photo-1557926005-012bd4382a0d | Alina Karpenko | https://unsplash.com/photos/XEmaJaM-4nE |

## 群和机器人

[DiceBear](https://www.dicebear.com/) 9.x 的 Shapes 风格,CC0 1.0 公有领域授权:
`https://api.dicebear.com/9.x/shapes/png?seed=<seed>&size=128&backgroundColor=b6e3f4,c0aede,d1d4f9,ffd5dc,ffdfbf,c7f0d8`

| 文件 | seed |
|---|---|
| group-member-center.png | g02 |
| group-product-design.png | g06 |
| group-weekly.png | g11 |
| bot-weekly.png | g05 |
