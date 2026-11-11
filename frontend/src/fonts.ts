export const font = {
  regular: "Jakarta-Regular",
  medium: "Jakarta-Medium",
  semibold: "Jakarta-SemiBold",
  bold: "Jakarta-Bold",
  extrabold: "Jakarta-ExtraBold",
};

export const fontAssets = {
  [font.regular]: require("../assets/fonts/PlusJakartaSans-Regular.ttf"),
  [font.medium]: require("../assets/fonts/PlusJakartaSans-Medium.ttf"),
  [font.semibold]: require("../assets/fonts/PlusJakartaSans-SemiBold.ttf"),
  [font.bold]: require("../assets/fonts/PlusJakartaSans-Bold.ttf"),
  [font.extrabold]: require("../assets/fonts/PlusJakartaSans-ExtraBold.ttf"),
};

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
export const radius = { sm: 6, md: 12, lg: 20, pill: 999 };
