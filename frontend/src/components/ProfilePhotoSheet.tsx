import * as ImagePicker from "expo-image-picker";
import React, { useState } from "react";
import { Linking, Text } from "react-native";

import { api, BASE, TOKEN_KEY } from "@/src/api";
import { Avatar } from "@/src/components/Avatar";
import { Button, Sheet, useToast } from "@/src/components/ui";
import { font } from "@/src/fonts";
import { useTheme } from "@/src/theme";
import { uploadForm } from "@/src/utils/upload";
import { storage } from "@/src/utils/storage";

type Props = {
  visible: boolean;
  onClose: () => void;
  userId: string;
  name: string;
  photo: string | null;
  onSaved: (path: string) => void;
  endpoint?: string; // "/courier/profile-photo" or "/biz/photo"
  title?: string;
  hint?: string;
  preview?: React.ReactNode;
};

// Courier (or business) picks or takes a photo; the admin and others see it.
export function ProfilePhotoSheet({ visible, onClose, userId, name, photo, onSaved, endpoint = "/courier/profile-photo", title = "Tu foto de perfil", hint, preview }: Props) {
  const { colors } = useTheme();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [camBlocked, setCamBlocked] = useState(false);

  const upload = async (a: ImagePicker.ImagePickerAsset) => {
    setBusy(true);
    try {
      const token = await storage.secureGet<string | null>(TOKEN_KEY, null);
      let path: string | null = null;
      try {
        const res = await uploadForm(`${BASE}${endpoint}`, {
          headers: { Authorization: `Bearer ${token}` },
          files: { file: { uri: a.uri, name: a.fileName ?? "foto.jpg", mimeType: a.mimeType ?? "image/jpeg" } },
        });
        if (res.ok) {
          const j = await res.json();
          path = j.profile_photo ?? j.photo;
        }
      } catch {
        path = null;
      }
      if (!path) {
        if (!a.base64) throw new Error("No se pudo subir la foto");
        const j = await api<{ profile_photo?: string; photo?: string }>(`${endpoint}-b64`, { method: "POST", body: { data: a.base64, mime: a.mimeType ?? "image/jpeg" } });
        path = (j.profile_photo ?? j.photo) as string;
      }
      onSaved(path);
      toast("Foto actualizada");
      onClose();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Error al subir la foto", "error");
    } finally {
      setBusy(false);
    }
  };

  const opts: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], quality: 0.5, base64: true, allowsEditing: true, aspect: [1, 1] };
  const fromCamera = async () => {
    let p = await ImagePicker.getCameraPermissionsAsync();
    if (!p.granted && p.canAskAgain) p = await ImagePicker.requestCameraPermissionsAsync();
    if (!p.granted) {
      setCamBlocked(!p.canAskAgain);
      return;
    }
    const r = await ImagePicker.launchCameraAsync(opts);
    if (!r.canceled) upload(r.assets[0]);
  };
  const fromGallery = async () => {
    const r = await ImagePicker.launchImageLibraryAsync(opts);
    if (!r.canceled) upload(r.assets[0]);
  };

  return (
    <Sheet testID="profile-photo-sheet" visible={visible} onClose={onClose} title={title}>
      {preview ?? <Avatar userId={userId} name={name} hasPhoto={!!photo} version={photo} size={96} />}
      <Text style={{ fontFamily: font.medium, fontSize: 14, color: colors.muted }}>
        {hint ?? "El administrador y los comercios verán esta foto para reconocerte al recoger los pedidos."}
      </Text>
      <Button testID="profile-photo-camera" title="Hacer una foto" icon="camera" loading={busy} onPress={fromCamera} />
      <Button testID="profile-photo-gallery" title="Elegir de la galería" icon="images-outline" variant="secondary" disabled={busy} onPress={fromGallery} />
      {camBlocked && <Button testID="profile-camera-settings" title="Activar cámara en ajustes" icon="settings-outline" variant="ghost" onPress={() => Linking.openSettings()} />}
    </Sheet>
  );
}
